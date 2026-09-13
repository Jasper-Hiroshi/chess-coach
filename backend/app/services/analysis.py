from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Game, Mistake, Move, MoveAssessment, PositionAnalysis, TrainingItem, utcnow
from ..protocols import ChessEngine


PIECE_NAMES = {
    chess.PAWN: "兵",
    chess.KNIGHT: "马",
    chess.BISHOP: "象",
    chess.ROOK: "车",
    chess.QUEEN: "后",
    chess.KING: "王",
}
SEVERITY_WEIGHT = {"normal": 0, "inaccuracy": 1, "mistake": 2, "blunder": 4}


def expected_score(line: dict[str, Any], color: chess.Color) -> float:
    wdl = line["wdl_white"]
    if color == chess.WHITE:
        return (2 * wdl["wins"] + wdl["draws"]) / 2000
    return (2 * wdl["losses"] + wdl["draws"]) / 2000


def severity_from_loss(loss: float) -> str:
    if loss < 0.05:
        return "normal"
    if loss < 0.10:
        return "inaccuracy"
    if loss < 0.20:
        return "mistake"
    return "blunder"


def cache_key(fen: str, nodes: int, multipv: int, root_moves: tuple[str, ...], version: str) -> str:
    payload = {
        "fen": fen,
        "nodes": nodes,
        "multipv": multipv,
        "root_moves": sorted(root_moves),
        "engine": version,
        "options": {"Threads": 1, "Hash": 256, "Ponder": False},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def analyze_cached(
    session: Session,
    engine: ChessEngine,
    fen: str,
    *,
    nodes: int,
    multipv: int,
    root_moves: tuple[str, ...] = (),
) -> PositionAnalysis:
    settings = get_settings()
    key = cache_key(fen, nodes, multipv, root_moves, settings.analysis_version)
    cached = session.scalar(select(PositionAnalysis).where(PositionAnalysis.cache_key == key))
    if cached:
        return cached
    lines = engine.analyze(fen, nodes=nodes, multipv=multipv, root_moves=root_moves)
    first = lines[0]
    wdl = first["wdl_white"]
    cached = PositionAnalysis(
        cache_key=key,
        fen=fen,
        engine_version=settings.analysis_version,
        nodes=nodes,
        multipv=multipv,
        uci_options={"Threads": 1, "Hash": 256, "Ponder": False, "root_moves": list(root_moves)},
        wdl_white_win=wdl["wins"],
        wdl_draw=wdl["draws"],
        wdl_white_loss=wdl["losses"],
        expected_score_white=first["expected_score_white"],
        score_cp=first.get("score_cp_white"),
        mate_in=first.get("mate_white"),
        best_move_uci=first.get("best_move_uci"),
        lines=lines,
    )
    session.add(cached)
    session.flush()
    return cached


def perspective_score(analysis: PositionAnalysis, color: chess.Color) -> float:
    return analysis.expected_score_white if color == chess.WHITE else 1 - analysis.expected_score_white


def mate_event(before: PositionAnalysis, played: PositionAnalysis, color: chess.Color) -> str | None:
    before_mate = before.mate_in
    played_mate = played.mate_in
    winning_sign = 1 if color == chess.WHITE else -1
    if before_mate and before_mate * winning_sign > 0 and (not played_mate or played_mate * winning_sign <= 0):
        return "missed_mate"
    if (not before_mate or before_mate * winning_sign >= 0) and played_mate and played_mate * winning_sign < 0:
        return "allowed_mate"
    return None


def safe_san(board: chess.Board, uci: str | None) -> str | None:
    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
        return board.san(move) if move in board.legal_moves else uci
    except ValueError:
        return uci


def extract_fact(
    move_row: Move,
    best: PositionAnalysis,
    played: PositionAnalysis,
    event: str | None,
    loss: float,
) -> tuple[str, dict[str, Any], str]:
    board = chess.Board(move_row.fen_before)
    best_san = safe_san(board, best.best_move_uci) or "推荐着"
    if event == "allowed_mate":
        facts = {"played_san": move_row.san, "best_san": best_san, "loss_percent": round(loss * 100)}
        return "allowed_mate", facts, f"{move_row.san} 之后，对手获得强制将杀；{best_san} 可以避开这一结果。"
    if event == "missed_mate":
        facts = {"played_san": move_row.san, "best_san": best_san, "loss_percent": round(loss * 100)}
        return "missed_mate", facts, f"这里 {best_san} 可以形成强制将杀；实战的 {move_row.san} 放走了机会。"

    played_lines = played.lines or []
    pv = played_lines[0].get("pv", []) if played_lines else []
    if len(pv) >= 2:
        try:
            played_move = chess.Move.from_uci(pv[0])
            board.push(played_move)
            reply = chess.Move.from_uci(pv[1])
            captured = board.piece_at(reply.to_square) if reply in board.legal_moves and board.is_capture(reply) else None
            if captured and captured.color != board.turn and captured.piece_type != chess.PAWN:
                reply_san = board.san(reply)
                theme = "hung_piece" if reply.to_square == played_move.to_square else "immediate_material_loss"
                facts = {
                    "played_san": move_row.san,
                    "best_san": best_san,
                    "reply_san": reply_san,
                    "piece_name": PIECE_NAMES[captured.piece_type],
                    "square": chess.square_name(reply.to_square),
                    "loss_percent": round(loss * 100),
                }
                explanation = f"{move_row.san} 后，对手可用 {reply_san} 立即吃掉{facts['piece_name']}；先比较 {best_san}。"
                return theme, facts, explanation
        except (ValueError, IndexError):
            pass

    original = chess.Board(move_row.fen_before)
    try:
        moved = chess.Move.from_uci(move_row.uci)
        piece = original.piece_at(moved.from_square)
    except ValueError:
        piece = None
    if move_row.ply <= 12 and piece and piece.piece_type == chess.QUEEN and not original.is_capture(moved) and not original.gives_check(moved):
        facts = {"played_san": move_row.san, "best_san": best_san, "loss_percent": round(loss * 100)}
        return "early_queen_move", facts, f"开局阶段的 {move_row.san} 让后过早行动；优先比较发展轻子的 {best_san}。"
    if move_row.clock_ms is not None and move_row.clock_ms <= 60_000:
        facts = {"played_san": move_row.san, "best_san": best_san, "seconds": round(move_row.clock_ms / 1000), "loss_percent": round(loss * 100)}
        return "time_trouble", facts, f"走这一步后仅剩约 {facts['seconds']} 秒；比较 {best_san}，并把复杂计算留给关键局面。"
    facts = {"played_san": move_row.san, "best_san": best_san, "loss_percent": round(loss * 100)}
    return "calculation", facts, f"{move_row.san} 使期望得分下降约 {facts['loss_percent']}%；建议比较 {best_san} 与实战变化。"


def analyze_game(session: Session, game: Game, engine: ChessEngine, progress=None) -> dict[str, Any]:
    settings = get_settings()
    moves = session.scalars(select(Move).where(Move.game_id == game.id).order_by(Move.ply)).all()
    player_color = chess.WHITE if game.player_color == "white" else chess.BLACK
    game.analysis_status = "running"
    session.commit()
    position_cache: dict[str, PositionAnalysis] = {}
    all_fens = [moves[0].fen_before] + [move.fen_after for move in moves] if moves else []
    for index, fen in enumerate(all_fens):
        if progress:
            progress(index, len(all_fens), f"快速扫描 {index + 1}/{len(all_fens)}")
        position_cache[fen] = analyze_cached(
            session, engine, fen, nodes=settings.analysis_fast_nodes, multipv=1
        )
        session.commit()

    session.execute(
        delete(MoveAssessment).where(
            MoveAssessment.move_id.in_([move.id for move in moves]),
            MoveAssessment.analysis_version == settings.analysis_version,
        )
    )
    session.commit()
    mistake_count = 0
    for index, move_row in enumerate(moves):
        mover = chess.WHITE if move_row.side_to_move == "white" else chess.BLACK
        if mover != player_color:
            continue
        before_fast = position_cache[move_row.fen_before]
        after_fast = position_cache[move_row.fen_after]
        quick_loss = perspective_score(before_fast, mover) - perspective_score(after_fast, mover)
        needs_deep = quick_loss >= 0.04 or mate_event(before_fast, after_fast, mover) is not None
        before = before_fast
        played = after_fast
        if needs_deep:
            if progress:
                progress(index, len(moves), f"复核第 {(move_row.ply + 1) // 2} 回合")
            before = analyze_cached(session, engine, move_row.fen_before, nodes=settings.analysis_deep_nodes, multipv=3)
            played = analyze_cached(
                session,
                engine,
                move_row.fen_before,
                nodes=settings.analysis_deep_nodes,
                multipv=1,
                root_moves=(move_row.uci,),
            )
            loss = max(0.0, perspective_score(before, mover) - perspective_score(played, mover))
        else:
            loss = max(0.0, quick_loss)
        event = mate_event(before, played, mover)
        severity = "blunder" if event else severity_from_loss(loss)
        assessment = MoveAssessment(
            move_id=move_row.id,
            analysis_version=settings.analysis_version,
            before_analysis_id=before.id,
            after_analysis_id=played.id,
            expected_loss=loss,
            severity=severity,
            forced_mate_changed=event is not None,
            search_unstable=quick_loss < -0.02,
        )
        session.add(assessment)
        session.flush()
        if severity != "normal":
            theme, facts, explanation = extract_fact(move_row, before, played, event, loss)
            board = chess.Board(move_row.fen_before)
            best_san = safe_san(board, before.best_move_uci)
            mistake = Mistake(
                move_assessment_id=assessment.id,
                theme=theme,
                facts=facts,
                explanation_zh=explanation,
                recommended_move_uci=before.best_move_uci,
                recommended_move_san=best_san,
                priority_score=SEVERITY_WEIGHT[severity] * (1 + loss),
            )
            session.add(mistake)
            session.flush()
            mistake_count += 1
            if severity in {"mistake", "blunder"} and before.best_move_uci and not assessment.search_unstable:
                existing_item = session.scalar(select(TrainingItem).where(TrainingItem.mistake_id == mistake.id))
                if existing_item is None:
                    top_lines = before.lines or []
                    accepted = [line["best_move_uci"] for line in top_lines if line.get("best_move_uci")]
                    solution = top_lines[0].get("pv", [])[:6] if top_lines else []
                    session.add(
                        TrainingItem(
                            profile_id=game.profile_id,
                            mistake_id=mistake.id,
                            fen=move_row.fen_before,
                            side_to_move=move_row.side_to_move,
                            answer_moves=accepted[:3],
                            solution_pv=solution,
                            theme=theme,
                            due_at=utcnow(),
                        )
                    )
        session.commit()
    game.analysis_status = "complete"
    session.commit()
    if progress:
        progress(len(moves), len(moves), "分析完成")
    return {"game_id": game.id, "mistake_count": mistake_count, "engine_version": settings.analysis_version}


def aggregate_themes(session: Session, profile_id: str, limit_games: int = 20) -> Counter:
    game_ids = session.scalars(
        select(Game.id).where(Game.profile_id == profile_id).order_by(Game.played_at.desc()).limit(limit_games)
    ).all()
    if not game_ids:
        return Counter()
    themes = session.scalars(
        select(Mistake.theme)
        .join(MoveAssessment, Mistake.move_assessment_id == MoveAssessment.id)
        .join(Move, MoveAssessment.move_id == Move.id)
        .where(Move.game_id.in_(game_ids))
    ).all()
    return Counter(themes)

