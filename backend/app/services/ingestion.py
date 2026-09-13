from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Any

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ArchiveFetchState, Game, Move, PlayerProfile, utcnow
from ..protocols import ArchiveRef, GameSource


def parse_clock_ms(node: chess.pgn.ChildNode) -> int | None:
    clock = node.clock()
    return round(clock * 1000) if clock is not None else None


def classify_phase(board: chess.Board, ply: int) -> str:
    non_pawn = sum(
        len(board.pieces(piece_type, color)) * value
        for color in chess.COLORS
        for piece_type, value in ((chess.KNIGHT, 3), (chess.BISHOP, 3), (chess.ROOK, 5), (chess.QUEEN, 9))
    )
    if ply <= 20 and (board.has_kingside_castling_rights(chess.WHITE) or board.has_kingside_castling_rights(chess.BLACK)):
        return "opening"
    queens_remaining = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if non_pawn <= 20 or (queens_remaining == 0 and non_pawn <= 30):
        return "endgame"
    return "middlegame"


def parse_played_at(headers: chess.pgn.Headers, fallback_epoch: int | None) -> datetime:
    date = headers.get("UTCDate") or headers.get("Date")
    time_value = headers.get("UTCTime") or "00:00:00"
    if date and date != "????.??.??":
        try:
            return datetime.strptime(f"{date} {time_value}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_epoch, tz=timezone.utc) if fallback_epoch else utcnow()


def normalized_pgn_hash(pgn_game: chess.pgn.Game, raw_pgn: str) -> str:
    if pgn_game.errors:
        return hashlib.sha256(raw_pgn.encode("utf-8")).hexdigest()
    board = pgn_game.board()
    moves: list[str] = []
    for move in pgn_game.mainline_moves():
        moves.append(move.uci())
        board.push(move)
    stable = "\0".join(
        [
            pgn_game.headers.get(key, "")
            for key in ("UTCDate", "UTCTime", "White", "Black", "Result", "TimeControl")
        ]
        + moves
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def ingest_game(session: Session, profile: PlayerProfile, source_game: dict[str, Any]) -> tuple[Game, bool]:
    raw_pgn = source_game.get("pgn") or ""
    parsed = chess.pgn.read_game(io.StringIO(raw_pgn)) if raw_pgn else None
    if parsed is None:
        pgn_hash = hashlib.sha256(raw_pgn.encode()).hexdigest()
        existing = session.scalar(select(Game).where(Game.profile_id == profile.id, Game.pgn_hash == pgn_hash))
        if existing:
            return existing, False
        game = Game(
            profile_id=profile.id,
            source_game_id=source_game.get("uuid"),
            source_url=source_game.get("url", ""),
            pgn_hash=pgn_hash,
            raw_pgn=raw_pgn,
            parse_status="invalid",
            parse_error="PGN 为空或无法解析",
            rules=source_game.get("rules", "unknown"),
            rated=bool(source_game.get("rated")),
            time_class=source_game.get("time_class", "unknown"),
            time_control=source_game.get("time_control", "-"),
            white_name=source_game.get("white", {}).get("username", "?"),
            black_name=source_game.get("black", {}).get("username", "?"),
            result="*",
            played_at=parse_played_at({}, source_game.get("end_time")),
            player_color="white",
            headers={},
        )
        session.add(game)
        session.flush()
        return game, True

    pgn_hash = normalized_pgn_hash(parsed, raw_pgn)
    source_id = source_game.get("uuid")
    existing = None
    if source_id:
        existing = session.scalar(select(Game).where(Game.source == "chess_com", Game.source_game_id == source_id))
    existing = existing or session.scalar(select(Game).where(Game.profile_id == profile.id, Game.pgn_hash == pgn_hash))
    if existing:
        return existing, False

    headers = dict(parsed.headers)
    white = headers.get("White", source_game.get("white", {}).get("username", "?"))
    black = headers.get("Black", source_game.get("black", {}).get("username", "?"))
    player_is_white = white.lower() == profile.chess_com_username_normalized
    white_rating = _int_or_none(headers.get("WhiteElo") or source_game.get("white", {}).get("rating"))
    black_rating = _int_or_none(headers.get("BlackElo") or source_game.get("black", {}).get("rating"))
    errors = "; ".join(str(error) for error in parsed.errors)
    eco_url = headers.get("ECOUrl") or source_game.get("eco") or ""
    opening_name = eco_url.rstrip("/").split("/")[-1].replace("-", " ") if eco_url else None
    game = Game(
        profile_id=profile.id,
        source_game_id=source_id,
        source_url=source_game.get("url") or headers.get("Link", ""),
        pgn_hash=pgn_hash,
        raw_pgn=raw_pgn,
        parse_status="invalid" if errors else "valid",
        parse_error=errors or None,
        rules=source_game.get("rules", "chess"),
        rated=bool(source_game.get("rated", True)),
        time_class=source_game.get("time_class", "rapid"),
        time_control=headers.get("TimeControl", source_game.get("time_control", "-")),
        white_name=white,
        black_name=black,
        white_rating=white_rating,
        black_rating=black_rating,
        result=headers.get("Result", "*"),
        termination=headers.get("Termination"),
        opening_name=opening_name,
        eco=headers.get("ECO"),
        played_at=parse_played_at(parsed.headers, source_game.get("end_time")),
        player_color="white" if player_is_white else "black",
        player_rating=white_rating if player_is_white else black_rating,
        opponent_rating=black_rating if player_is_white else white_rating,
        headers=headers,
        analysis_status="not_queued" if errors or source_game.get("rules", "chess") != "chess" else "queued",
    )
    session.add(game)
    session.flush()

    if not errors:
        board = parsed.board()
        for ply, node in enumerate(parsed.mainline(), start=1):
            move = node.move
            fen_before = board.fen(en_passant="legal")
            side = "white" if board.turn == chess.WHITE else "black"
            san = board.san(move)
            phase = classify_phase(board, ply)
            board.push(move)
            session.add(
                Move(
                    game_id=game.id,
                    ply=ply,
                    side_to_move=side,
                    san=san,
                    uci=move.uci(),
                    fen_before=fen_before,
                    fen_after=board.fen(en_passant="legal"),
                    clock_ms=parse_clock_ms(node),
                    phase=phase,
                    is_book=phase == "opening",
                )
            )
    return game, True


def sync_profile(session: Session, profile: PlayerProfile, source: GameSource, progress=None) -> dict[str, Any]:
    archives = source.list_archives(profile.chess_com_username_normalized)
    summary = {"archives": len(archives), "new_games": 0, "duplicates": 0, "invalid": 0, "failed_months": []}
    for index, archive in enumerate(archives, start=1):
        if progress:
            progress(index - 1, len(archives), f"正在导入 {archive.month}")
        state = session.scalar(
            select(ArchiveFetchState).where(
                ArchiveFetchState.profile_id == profile.id,
                ArchiveFetchState.archive_url == archive.url,
            )
        )
        if state is None:
            state = ArchiveFetchState(profile_id=profile.id, archive_url=archive.url, archive_month=archive.month)
            session.add(state)
            session.flush()
        try:
            result = source.fetch_archive(archive, etag=state.etag, last_modified=state.last_modified)
            state.last_fetched_at = utcnow()
            if result.status == "not_modified":
                state.fetch_status = "not_modified"
                session.commit()
                continue
            for source_game in result.games:
                game, created = ingest_game(session, profile, source_game)
                summary["new_games" if created else "duplicates"] += 1
                if created and game.parse_status == "invalid":
                    summary["invalid"] += 1
            state.etag = result.etag
            state.last_modified = result.last_modified
            state.fetch_status = "success"
            state.last_error = None
            session.commit()
        except Exception as exc:  # a month failure must not roll back successful months
            session.rollback()
            state = session.scalar(select(ArchiveFetchState).where(ArchiveFetchState.id == state.id))
            if state:
                state.fetch_status = "failed"
                state.last_error = str(exc)
                state.last_fetched_at = utcnow()
                session.commit()
            summary["failed_months"].append({"month": archive.month, "error": str(exc)})
    if progress:
        progress(len(archives), len(archives), "同步完成")
    return summary


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "", "?") else None
    except (TypeError, ValueError):
        return None
