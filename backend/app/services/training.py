from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Game, Mistake, Move, MoveAssessment, PlayerProfile, TrainingAttempt, TrainingItem, WeeklyPlan
from .analysis import aggregate_themes


INTERVAL_DAYS = (1, 3, 7, 14, 30)
THEME_LABELS = {
    "allowed_mate": "避免一步被杀",
    "missed_mate": "寻找强制将杀",
    "hung_piece": "子力安全扫描",
    "immediate_material_loss": "先看对方的吃子",
    "early_queen_move": "优先发展轻子",
    "time_trouble": "关键局面时间分配",
    "calculation": "将军、吃子、威胁计算",
}


def apply_attempt(
    session: Session,
    item: TrainingItem,
    move_uci: str,
    used_hint: bool,
    elapsed_ms: int,
    attempt_id: str | None = None,
) -> TrainingAttempt:
    attempt_key = attempt_id or str(uuid.uuid4())
    existing = session.scalar(select(TrainingAttempt).where(TrainingAttempt.attempt_id == attempt_key))
    if existing:
        return existing
    previous = item.interval_level
    correct = move_uci in (item.answer_moves or []) and not used_hint
    if correct:
        item.interval_level = min(previous + 1, len(INTERVAL_DAYS) - 1)
        days = INTERVAL_DAYS[min(previous, len(INTERVAL_DAYS) - 1)]
    else:
        item.interval_level = 0
        days = 1
    item.due_at = datetime.now(timezone.utc) + timedelta(days=days)
    attempt = TrainingAttempt(
        attempt_id=attempt_key,
        training_item_id=item.id,
        submitted_move_uci=move_uci,
        correct=correct,
        used_hint=used_hint,
        elapsed_ms=elapsed_ms,
        previous_level=previous,
        new_level=item.interval_level,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def generate_weekly_plan(session: Session, profile: PlayerProfile) -> WeeklyPlan:
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    existing = session.scalar(
        select(WeeklyPlan).where(
            WeeklyPlan.profile_id == profile.id,
            WeeklyPlan.week_start == week_start,
            WeeklyPlan.algorithm_version == "weekly-v1",
        )
    )
    themes = aggregate_themes(session, profile.id)
    if themes:
        focuses = [
            {
                "theme": theme,
                "title": THEME_LABELS.get(theme, "局面计算"),
                "evidence": f"最近对局中出现 {count} 次",
                "target_sessions": min(5, max(2, count)),
            }
            for theme, count in themes.most_common(3)
        ]
    else:
        focuses = [
            {"theme": "cct_scan", "title": "先检查对方的将军与吃子", "evidence": "冷启动基础训练", "target_sessions": 5},
            {"theme": "king_safety", "title": "完成发展并保护王", "evidence": "冷启动基础训练", "target_sessions": 3},
            {"theme": "stable_opening", "title": "固定首回合应对", "evidence": "样本不足，先建立熟悉度", "target_sessions": 2},
        ]
    activities = [
        {"title": "4 局 15+10 实战", "minutes": 120},
        {"title": "先自评，再看引擎", "minutes": 100},
        {"title": "5 次到期训练", "minutes": 80},
        {"title": "残局 / 开局复习", "minutes": 40},
    ]
    if existing:
        existing.focus_topics = focuses
        existing.activities = activities
        plan = existing
    else:
        plan = WeeklyPlan(profile_id=profile.id, week_start=week_start, focus_topics=focuses, activities=activities)
        session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def progress_report(session: Session, profile: PlayerProfile, time_class: str) -> dict:
    games = session.scalars(
        select(Game)
        .where(Game.profile_id == profile.id, Game.time_class == time_class)
        .order_by(Game.played_at.desc())
        .limit(40)
    ).all()

    def window_metrics(window: list[Game]) -> dict:
        if not window:
            return {"count": 0, "blunders_per_100": None, "mistakes_per_100": None}
        ids = [game.id for game in window]
        move_count = session.scalar(select(func.count(Move.id)).where(Move.game_id.in_(ids))) or 0
        severity_counts = Counter(
            session.scalars(
                select(MoveAssessment.severity)
                .join(Move, MoveAssessment.move_id == Move.id)
                .where(Move.game_id.in_(ids))
            ).all()
        )
        denominator = max(move_count, 1)
        return {
            "count": len(window),
            "from": min(game.played_at for game in window).isoformat(),
            "to": max(game.played_at for game in window).isoformat(),
            "blunders_per_100": round(severity_counts["blunder"] * 100 / denominator, 1),
            "mistakes_per_100": round((severity_counts["mistake"] + severity_counts["blunder"]) * 100 / denominator, 1),
        }

    current = window_metrics(games[:20])
    baseline = window_metrics(games[20:40])
    trend = len(games) >= 40
    current_rating = next((game.player_rating for game in games if game.player_rating is not None), None)
    message = (
        "样本足够：比较最近 20 局与此前 20 局。"
        if trend
        else f"目前只有 {len(games)} 局同类对局；至少 40 局才进行前后窗口比较。"
    )
    metrics = [
        {"key": "blunders_per_100", "label": "严重失误 / 100 手", "current": current["blunders_per_100"], "baseline": baseline["blunders_per_100"] if trend else None, "unit": "次", "direction": "lower_is_better"},
        {"key": "mistakes_per_100", "label": "关键错误 / 100 手", "current": current["mistakes_per_100"], "baseline": baseline["mistakes_per_100"] if trend else None, "unit": "次", "direction": "lower_is_better"},
    ]
    return {
        "time_class": time_class,
        "current_rating": current_rating,
        "target_rating": profile.target_rating,
        "current_window": current,
        "baseline_window": baseline,
        "metrics": metrics,
        "trend_available": trend,
        "sample_message": message,
        "metric_version": "metrics-v1",
    }
