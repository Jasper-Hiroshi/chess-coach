from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import chess
import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .db import get_db
from .errors import AppError
from .integrations.lichess import LichessOpeningExplorer
from .models import (
    AnalysisJob,
    Game,
    Mistake,
    Move,
    MoveAssessment,
    OpeningExplorerCache,
    PlayerProfile,
    PositionAnalysis,
    TrainingItem,
    WeeklyPlan,
)
from .queue import create_job
from .schemas import (
    ChessComImportRequest,
    DashboardView,
    GameDetail,
    GameList,
    GameReview,
    GameSummary,
    JobCreated,
    JobRead,
    MistakeView,
    OpeningMoveView,
    OpeningTreeView,
    ProgressReport,
    ReviewMove,
    SyncRequest,
    TrainingAttemptCreate,
    TrainingAttemptResult,
    TrainingItemCreate,
    TrainingItemCreated,
    TrainingItemView,
    WeeklyPlanView,
)
from .services.training import apply_attempt, generate_weekly_plan, progress_report


router = APIRouter(prefix="/api/v1")


def current_profile(session: Session) -> PlayerProfile:
    profile = session.scalar(select(PlayerProfile).order_by(PlayerProfile.created_at).limit(1))
    if not profile:
        raise AppError("profile_not_configured", "请先导入 Chess.com 账号", status_code=404)
    return profile


def game_mistake_counts(session: Session, game_ids: list[str]) -> dict[str, int]:
    if not game_ids:
        return {}
    rows = session.execute(
        select(Move.game_id, func.count(Mistake.id))
        .join(MoveAssessment, MoveAssessment.move_id == Move.id)
        .join(Mistake, Mistake.move_assessment_id == MoveAssessment.id)
        .where(Move.game_id.in_(game_ids))
        .group_by(Move.game_id)
    ).all()
    return dict(rows)


def to_game_summary(game: Game, mistake_count: int = 0) -> GameSummary:
    return GameSummary.model_validate(game).model_copy(update={"mistake_count": mistake_count})


@router.post("/imports/chess-com", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
def import_chess_com(body: ChessComImportRequest, session: Session = Depends(get_db)):
    normalized = body.username.strip().lower()
    profile = session.scalar(select(PlayerProfile).where(PlayerProfile.chess_com_username_normalized == normalized))
    if profile is None:
        profile = PlayerProfile(chess_com_username=body.username.strip(), chess_com_username_normalized=normalized)
        session.add(profile)
        session.commit()
        session.refresh(profile)
    job, deduplicated = create_job(session, "sync_games", {"profile_id": profile.id}, f"sync:{profile.id}", priority=2)
    return JobCreated(profile_id=profile.id, job_id=job.id, deduplicated=deduplicated)


@router.post("/sync", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
def sync_games(body: SyncRequest, session: Session = Depends(get_db)):
    profile = session.get(PlayerProfile, body.profile_id) if body.profile_id else current_profile(session)
    if not profile:
        raise AppError("profile_not_found", "未找到该账号配置", status_code=404)
    job, deduplicated = create_job(session, "sync_games", {"profile_id": profile.id}, f"sync:{profile.id}", priority=2)
    return JobCreated(profile_id=profile.id, job_id=job.id, deduplicated=deduplicated)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_db)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise AppError("job_not_found", "未找到该任务", status_code=404)
    return job


@router.delete("/jobs/{job_id}", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def cancel_job(job_id: str, session: Session = Depends(get_db)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise AppError("job_not_found", "未找到该任务", status_code=404)
    if job.status == "pending":
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    elif job.status == "running":
        job.cancel_requested = True
        job.current_step = "将在当前步骤结束后取消"
    session.commit()
    session.refresh(job)
    return job


@router.get("/games", response_model=GameList)
def list_games(
    time_class: str | None = None,
    color: str | None = None,
    result: str | None = None,
    analysis_status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    profile = current_profile(session)
    stmt = select(Game).where(Game.profile_id == profile.id).order_by(Game.played_at.desc()).limit(limit)
    if time_class:
        stmt = stmt.where(Game.time_class == time_class)
    if color:
        stmt = stmt.where(Game.player_color == color)
    if result:
        stmt = stmt.where(Game.result == result)
    if analysis_status:
        stmt = stmt.where(Game.analysis_status == analysis_status)
    games = session.scalars(stmt).all()
    counts = game_mistake_counts(session, [game.id for game in games])
    return GameList(items=[to_game_summary(game, counts.get(game.id, 0)) for game in games])


@router.get("/games/{game_id}", response_model=GameDetail)
def get_game(game_id: str, session: Session = Depends(get_db)):
    game = session.scalar(select(Game).options(selectinload(Game.moves)).where(Game.id == game_id))
    if not game:
        raise AppError("game_not_found", "未找到该对局", status_code=404)
    count = game_mistake_counts(session, [game.id]).get(game.id, 0)
    return GameDetail(**to_game_summary(game, count).model_dump(), raw_pgn=game.raw_pgn, moves=game.moves)


@router.post("/games/{game_id}/analysis", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
def create_analysis(game_id: str, force: bool = False, session: Session = Depends(get_db)):
    game = session.get(Game, game_id)
    if not game:
        raise AppError("game_not_found", "未找到该对局", status_code=404)
    if force:
        game.analysis_status = "queued"
        session.commit()
    job, deduplicated = create_job(session, "analyze_game", {"game_id": game.id}, f"analyze:{game.id}", priority=1)
    return JobCreated(profile_id=game.profile_id, job_id=job.id, deduplicated=deduplicated)


@router.get("/games/{game_id}/review", response_model=GameReview)
def review_game(game_id: str, session: Session = Depends(get_db)):
    game = session.scalar(select(Game).options(selectinload(Game.moves)).where(Game.id == game_id))
    if not game:
        raise AppError("game_not_found", "未找到该对局", status_code=404)
    assessments = session.scalars(
        select(MoveAssessment).join(Move).where(Move.game_id == game.id).options(selectinload(MoveAssessment.mistakes))
    ).all()
    by_move = {item.move_id: item for item in assessments}
    analysis_ids = {
        value for item in assessments for value in (item.before_analysis_id, item.after_analysis_id) if value
    }
    analyses = {item.id: item for item in session.scalars(select(PositionAnalysis).where(PositionAnalysis.id.in_(analysis_ids))).all()} if analysis_ids else {}
    training_by_mistake = {
        item.mistake_id: item.id
        for item in session.scalars(select(TrainingItem).where(TrainingItem.profile_id == game.profile_id)).all()
    }
    review_moves: list[ReviewMove] = []
    mistakes: list[MistakeView] = []
    for move in game.moves:
        assessment = by_move.get(move.id)
        before = analyses.get(assessment.before_analysis_id) if assessment else None
        after = analyses.get(assessment.after_analysis_id) if assessment else None
        pov = game.player_color
        before_score = before.expected_score_white if before and pov == "white" else (1 - before.expected_score_white if before else None)
        after_score = after.expected_score_white if after and pov == "white" else (1 - after.expected_score_white if after else None)
        review_moves.append(
            ReviewMove.model_validate(move).model_copy(
                update={
                    "expected_score_before": before_score,
                    "expected_score_after": after_score,
                    "severity": assessment.severity if assessment else "normal",
                }
            )
        )
        if assessment:
            for mistake in assessment.mistakes:
                lines = before.lines if before else []
                mistakes.append(
                    MistakeView(
                        id=mistake.id,
                        ply=move.ply,
                        severity=assessment.severity,
                        expected_score_loss=assessment.expected_loss,
                        themes=[mistake.theme],
                        explanation=mistake.explanation_zh,
                        facts=[{"label": key, "value": str(value)} for key, value in (mistake.facts or {}).items()],
                        best_move_san=mistake.recommended_move_san,
                        best_move_uci=mistake.recommended_move_uci,
                        played_move_san=move.san,
                        principal_variations=lines,
                        training_item_id=training_by_mistake.get(mistake.id),
                    )
                )
    count = len(mistakes)
    engine_version = assessments[0].analysis_version if assessments else None
    return GameReview(
        game=to_game_summary(game, count),
        analysis_status=game.analysis_status,
        player_color=game.player_color,
        engine_version=engine_version,
        moves=review_moves,
        mistakes=mistakes,
    )


@router.post("/training/items", response_model=TrainingItemCreated)
def create_training_item(body: TrainingItemCreate, session: Session = Depends(get_db)):
    existing = session.scalar(select(TrainingItem).where(TrainingItem.mistake_id == body.mistake_id))
    if existing:
        return TrainingItemCreated(training_item_id=existing.id, created=False)
    mistake = session.get(Mistake, body.mistake_id)
    if not mistake:
        raise AppError("mistake_not_found", "未找到该关键局面", status_code=404)
    assessment = session.get(MoveAssessment, mistake.move_assessment_id)
    move = session.get(Move, assessment.move_id) if assessment else None
    game = session.get(Game, move.game_id) if move else None
    if not assessment or not move or not game or not mistake.recommended_move_uci:
        raise AppError("training_unavailable", "这个局面暂时无法生成可靠训练题")
    before = session.get(PositionAnalysis, assessment.before_analysis_id)
    lines = before.lines if before else []
    item = TrainingItem(
        profile_id=game.profile_id,
        mistake_id=mistake.id,
        fen=move.fen_before,
        side_to_move=move.side_to_move,
        answer_moves=[line.get("best_move_uci") for line in lines if line.get("best_move_uci")][:3] or [mistake.recommended_move_uci],
        solution_pv=(lines[0].get("pv", [])[:6] if lines else [mistake.recommended_move_uci]),
        theme=mistake.theme,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return TrainingItemCreated(training_item_id=item.id, created=True)


@router.get("/training/queue", response_model=list[TrainingItemView])
def training_queue(limit: int = Query(default=20, ge=1, le=50), session: Session = Depends(get_db)):
    profile = current_profile(session)
    now = datetime.now(timezone.utc)
    items = session.scalars(
        select(TrainingItem)
        .where(TrainingItem.profile_id == profile.id, TrainingItem.suspended_at.is_(None), TrainingItem.due_at <= now)
        .order_by(TrainingItem.due_at)
        .limit(limit)
    ).all()
    return items


@router.post("/training/attempts", response_model=TrainingAttemptResult)
def submit_attempt(body: TrainingAttemptCreate, session: Session = Depends(get_db)):
    item = session.get(TrainingItem, body.training_item_id)
    if not item:
        raise AppError("training_item_not_found", "未找到该训练题", status_code=404)
    attempt = apply_attempt(session, item, body.move_uci, body.used_hint, body.elapsed_ms, body.attempt_id)
    return TrainingAttemptResult(
        correct=attempt.correct,
        previous_level=attempt.previous_level,
        new_level=attempt.new_level,
        due_at=item.due_at,
        solution_pv=item.solution_pv or [],
    )


def plan_view(plan: WeeklyPlan, sample_count: int) -> WeeklyPlanView:
    return WeeklyPlanView(
        id=plan.id,
        week_start=plan.week_start.isoformat(),
        focus_topics=plan.focus_topics,
        activities=plan.activities,
        sample_count=sample_count,
    )


@router.get("/plans/current", response_model=WeeklyPlanView)
def current_plan(session: Session = Depends(get_db)):
    profile = current_profile(session)
    plan = generate_weekly_plan(session, profile)
    count = session.scalar(select(func.count(Game.id)).where(Game.profile_id == profile.id)) or 0
    return plan_view(plan, count)


@router.post("/plans/generate", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
def generate_plan(session: Session = Depends(get_db)):
    profile = current_profile(session)
    key = f"plan:{profile.id}:{datetime.now(timezone.utc).date().isoformat()}"
    job, deduplicated = create_job(session, "generate_plan", {"profile_id": profile.id}, key)
    return JobCreated(profile_id=profile.id, job_id=job.id, deduplicated=deduplicated)


@router.get("/progress", response_model=ProgressReport)
def progress(time_class: str = "rapid", session: Session = Depends(get_db)):
    return progress_report(session, current_profile(session), time_class)


def explorer_cached(session: Session, fen: str, source: str) -> tuple[dict[str, Any], bool]:
    settings = get_settings()
    params = {"fen": fen, "source": source, "ratings": [1000, 1200, 1400], "speeds": ["rapid", "classical"]}
    key = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    cached = session.get(OpeningExplorerCache, key)
    if cached and cached.expires_at > now:
        return cached.response, False
    try:
        response = LichessOpeningExplorer().query(
            fen,
            source=source,
            ratings=(1000, 1200, 1400) if source == "lichess" else (),
            speeds=("rapid", "classical") if source == "lichess" else (),
        )
        expires = now + timedelta(hours=settings.opening_cache_hours)
        if cached:
            cached.response = response
            cached.expires_at = expires
            cached.fetched_at = now
        else:
            session.add(OpeningExplorerCache(cache_key=key, provider=source, request_params=params, response=response, expires_at=expires))
        session.commit()
        return response, False
    except httpx.HTTPError:
        return (cached.response if cached else {}), True


@router.get("/openings/tree", response_model=OpeningTreeView)
def opening_tree(
    color: str = "white",
    fen: str = chess.STARTING_FEN,
    session: Session = Depends(get_db),
):
    profile = current_profile(session)
    personal: dict[str, list[Game]] = defaultdict(list)
    games = session.scalars(select(Game).where(Game.profile_id == profile.id, Game.player_color == color)).all()
    for game in games:
        first = session.scalar(select(Move).where(Move.game_id == game.id, Move.fen_before == fen).order_by(Move.ply).limit(1))
        if first and first.side_to_move == color:
            personal[first.uci].append(game)
    lichess, stale_l = explorer_cached(session, fen, "lichess")
    masters, stale_m = explorer_cached(session, fen, "masters")
    lmap = {row.get("uci"): row for row in lichess.get("moves", [])}
    mmap = {row.get("uci"): row for row in masters.get("moves", [])}
    all_moves = set(personal) | set(lmap) | set(mmap)
    board = chess.Board(fen)
    rows: list[OpeningMoveView] = []
    for uci in all_moves:
        sample = len(personal.get(uci, []))
        confidence = "reliable" if sample >= 20 else "descriptive" if sample >= 5 else "insufficient"
        personal_score = None
        if sample >= 5:
            score = 0.0
            for game in personal[uci]:
                if game.result == "1/2-1/2":
                    score += 0.5
                elif (color == "white" and game.result == "1-0") or (color == "black" and game.result == "0-1"):
                    score += 1
            personal_score = round(score / sample, 3)
        try:
            san = board.san(chess.Move.from_uci(uci))
        except ValueError:
            san = uci
        lrow, mrow = lmap.get(uci, {}), mmap.get(uci, {})
        lcount = sum(int(lrow.get(key, 0)) for key in ("white", "draws", "black")) if lrow else None
        mcount = sum(int(mrow.get(key, 0)) for key in ("white", "draws", "black")) if mrow else None
        recommendation = "证据不足：先按开局原则评估" if sample < 5 else "已观察到个人使用记录"
        rows.append(OpeningMoveView(uci=uci, san=san, personal_count=sample, personal_score=personal_score, lichess_count=lcount, masters_count=mcount, confidence=confidence, recommendation=recommendation))
    rows.sort(key=lambda row: ((row.lichess_count or 0) + (row.masters_count or 0), row.personal_count), reverse=True)
    total = sum(len(values) for values in personal.values())
    confidence = "reliable" if total >= 20 else "descriptive" if total >= 5 else "insufficient"
    opening_name = (lichess.get("opening") or {}).get("name") or (masters.get("opening") or {}).get("name")
    return OpeningTreeView(fen=fen, color=color, sample_count=total, confidence=confidence, opening_name=opening_name, moves=rows[:12], offline_or_stale=stale_l or stale_m)


@router.get("/dashboard", response_model=DashboardView)
def dashboard(session: Session = Depends(get_db)):
    try:
        profile = current_profile(session)
    except AppError:
        blank_progress = {
            "time_class": "rapid", "current_rating": None, "target_rating": 900,
            "current_window": {"count": 0}, "baseline_window": {"count": 0}, "metrics": [],
            "trend_available": False, "sample_message": "导入对局后开始建立基线。", "metric_version": "metrics-v1"
        }
        blank_plan = WeeklyPlanView(week_start=datetime.now().date().isoformat(), focus_topics=[], activities=[], sample_count=0)
        return DashboardView(username=None, current_rating=None, target_rating=900, game_count=0, analysed_count=0, due_training_count=0, sync_status="not_configured", weekly_plan=blank_plan, recent_games=[], progress=ProgressReport(**blank_progress))
    games = session.scalars(select(Game).where(Game.profile_id == profile.id).order_by(Game.played_at.desc()).limit(5)).all()
    total = session.scalar(select(func.count(Game.id)).where(Game.profile_id == profile.id)) or 0
    analysed = session.scalar(select(func.count(Game.id)).where(Game.profile_id == profile.id, Game.analysis_status == "complete")) or 0
    due = session.scalar(select(func.count(TrainingItem.id)).where(TrainingItem.profile_id == profile.id, TrainingItem.due_at <= datetime.now(timezone.utc))) or 0
    counts = game_mistake_counts(session, [game.id for game in games])
    latest_job = session.scalar(select(AnalysisJob).where(AnalysisJob.job_type == "sync_games").order_by(AnalysisJob.created_at.desc()).limit(1))
    plan = generate_weekly_plan(session, profile)
    report = progress_report(session, profile, profile.default_time_class)
    return DashboardView(
        username=profile.chess_com_username,
        current_rating=report["current_rating"],
        target_rating=profile.target_rating,
        game_count=total,
        analysed_count=analysed,
        due_training_count=due,
        sync_status=latest_job.status if latest_job else "idle",
        weekly_plan=plan_view(plan, total),
        recent_games=[to_game_summary(game, counts.get(game.id, 0)) for game in games],
        progress=ProgressReport(**report),
    )


@router.get("/exports/games.pgn", response_class=PlainTextResponse)
def export_games(session: Session = Depends(get_db)):
    profile = current_profile(session)
    games = session.scalars(select(Game).where(Game.profile_id == profile.id).order_by(Game.played_at)).all()
    return PlainTextResponse("\n\n".join(game.raw_pgn for game in games), media_type="application/x-chess-pgn", headers={"Content-Disposition": "attachment; filename=chess-coach-games.pgn"})


@router.get("/exports/analysis.csv")
def export_analysis(session: Session = Depends(get_db)):
    profile = current_profile(session)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["game_id", "played_at", "ply", "played_move", "severity", "expected_loss", "theme", "recommended_move", "explanation"])
    rows = session.execute(
        select(Game, Move, MoveAssessment, Mistake)
        .join(Move, Move.game_id == Game.id)
        .join(MoveAssessment, MoveAssessment.move_id == Move.id)
        .join(Mistake, Mistake.move_assessment_id == MoveAssessment.id)
        .where(Game.profile_id == profile.id)
        .order_by(Game.played_at, Move.ply)
    ).all()
    for game, move, assessment, mistake in rows:
        writer.writerow([game.id, game.played_at.isoformat(), move.ply, move.san, assessment.severity, assessment.expected_loss, mistake.theme, mistake.recommended_move_san, mistake.explanation_zh])
    return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=chess-coach-analysis.csv"})
