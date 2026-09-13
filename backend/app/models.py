from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class PlayerProfile(Base):
    __tablename__ = "player_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chess_com_username: Mapped[str] = mapped_column(String(64))
    chess_com_username_normalized: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    target_rating: Mapped[int] = mapped_column(Integer, default=900)
    default_time_class: Mapped[str] = mapped_column(String(24), default="rapid")
    weekly_minutes: Mapped[int] = mapped_column(Integer, default=300)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    games: Mapped[list[Game]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ArchiveFetchState(Base):
    __tablename__ = "archive_fetch_states"
    __table_args__ = (UniqueConstraint("profile_id", "archive_url", name="uq_archive_profile_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True)
    archive_url: Mapped[str] = mapped_column(Text)
    archive_month: Mapped[str] = mapped_column(String(7))
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(24), default="never")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("profile_id", "pgn_hash", name="uq_game_profile_pgn_hash"),
        Index("ix_games_profile_played", "profile_id", "played_at", "id"),
        Index("uq_games_source_id", "source", "source_game_id", unique=True, postgresql_where=text("source_game_id IS NOT NULL"), sqlite_where=text("source_game_id IS NOT NULL")),
        CheckConstraint("player_color IN ('white','black')", name="ck_games_player_color"),
        CheckConstraint("analysis_status IN ('not_queued','queued','running','complete','failed')", name="ck_games_analysis_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(24), default="chess_com")
    source_game_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    pgn_hash: Mapped[str] = mapped_column(String(64))
    raw_pgn: Mapped[str] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(24), default="valid")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[str] = mapped_column(String(32), default="chess")
    rated: Mapped[bool] = mapped_column(Boolean, default=True)
    time_class: Mapped[str] = mapped_column(String(24), default="rapid")
    time_control: Mapped[str] = mapped_column(String(32), default="-")
    white_name: Mapped[str] = mapped_column(String(64))
    black_name: Mapped[str] = mapped_column(String(64))
    white_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(12), default="*")
    termination: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eco: Mapped[str | None] = mapped_column(String(8), nullable=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    player_color: Mapped[str] = mapped_column(String(8))
    player_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opponent_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    analysis_status: Mapped[str] = mapped_column(String(24), default="not_queued")
    review_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    profile: Mapped[PlayerProfile] = relationship(back_populates="games")
    moves: Mapped[list[Move]] = relationship(back_populates="game", cascade="all, delete-orphan", order_by="Move.ply")


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (
        UniqueConstraint("game_id", "ply", name="uq_move_game_ply"),
        CheckConstraint("phase IN ('opening','middlegame','endgame')", name="ck_moves_phase"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    side_to_move: Mapped[str] = mapped_column(String(8))
    san: Mapped[str] = mapped_column(String(24))
    uci: Mapped[str] = mapped_column(String(8))
    fen_before: Mapped[str] = mapped_column(Text)
    fen_after: Mapped[str] = mapped_column(Text)
    clock_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str] = mapped_column(String(24))
    is_book: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped[Game] = relationship(back_populates="moves")
    assessment: Mapped[MoveAssessment | None] = relationship(back_populates="move", cascade="all, delete-orphan", uselist=False)


class PositionAnalysis(Base):
    __tablename__ = "position_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fen: Mapped[str] = mapped_column(Text)
    engine_name: Mapped[str] = mapped_column(String(64), default="Stockfish")
    engine_version: Mapped[str] = mapped_column(String(64))
    nodes: Mapped[int] = mapped_column(Integer)
    multipv: Mapped[int] = mapped_column(Integer)
    uci_options: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    wdl_white_win: Mapped[int] = mapped_column(Integer)
    wdl_draw: Mapped[int] = mapped_column(Integer)
    wdl_white_loss: Mapped[int] = mapped_column(Integer)
    expected_score_white: Mapped[float] = mapped_column(Float)
    score_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mate_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_move_uci: Mapped[str | None] = mapped_column(String(8), nullable=True)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MoveAssessment(Base):
    __tablename__ = "move_assessments"
    __table_args__ = (
        UniqueConstraint("move_id", "analysis_version", name="uq_move_assessment_version"),
        CheckConstraint("severity IN ('normal','inaccuracy','mistake','blunder')", name="ck_assessment_severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    move_id: Mapped[str] = mapped_column(ForeignKey("moves.id", ondelete="CASCADE"), index=True)
    analysis_version: Mapped[str] = mapped_column(String(64))
    before_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("position_analyses.id"), nullable=True)
    after_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("position_analyses.id"), nullable=True)
    expected_loss: Mapped[float] = mapped_column(Float, default=0)
    severity: Mapped[str] = mapped_column(String(24), default="normal")
    forced_mate_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    search_unstable: Mapped[bool] = mapped_column(Boolean, default=False)

    move: Mapped[Move] = relationship(back_populates="assessment")
    mistakes: Mapped[list[Mistake]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class Mistake(Base):
    __tablename__ = "mistakes"
    __table_args__ = (UniqueConstraint("move_assessment_id", "theme", name="uq_mistake_theme"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    move_assessment_id: Mapped[str] = mapped_column(ForeignKey("move_assessments.id", ondelete="CASCADE"), index=True)
    theme: Mapped[str] = mapped_column(String(64))
    facts: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    explanation_zh: Mapped[str] = mapped_column(Text)
    recommended_move_uci: Mapped[str | None] = mapped_column(String(8), nullable=True)
    recommended_move_san: Mapped[str | None] = mapped_column(String(24), nullable=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0)

    assessment: Mapped[MoveAssessment] = relationship(back_populates="mistakes")


class TrainingItem(Base):
    __tablename__ = "training_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True)
    mistake_id: Mapped[str] = mapped_column(ForeignKey("mistakes.id", ondelete="CASCADE"), unique=True)
    fen: Mapped[str] = mapped_column(Text)
    side_to_move: Mapped[str] = mapped_column(String(8))
    answer_moves: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    solution_pv: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    theme: Mapped[str] = mapped_column(String(64))
    interval_level: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingAttempt(Base):
    __tablename__ = "training_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    training_item_id: Mapped[str] = mapped_column(ForeignKey("training_items.id", ondelete="CASCADE"), index=True)
    submitted_move_uci: Mapped[str] = mapped_column(String(8))
    correct: Mapped[bool] = mapped_column(Boolean)
    used_hint: Mapped[bool] = mapped_column(Boolean, default=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    previous_level: Mapped[int] = mapped_column(Integer)
    new_level: Mapped[int] = mapped_column(Integer)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (UniqueConstraint("profile_id", "week_start", "algorithm_version", name="uq_weekly_plan"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[datetime.date] = mapped_column(Date)
    focus_topics: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    activities: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="weekly-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True)
    time_class: Mapped[str] = mapped_column(String(24))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    game_ids: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    analysis_version: Mapped[str] = mapped_column(String(64))


class OpeningExplorerCache(Base):
    __tablename__ = "opening_explorer_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    request_params: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    response: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "run_after", "priority", "created_at"),
        Index("uq_jobs_active_dedupe", "dedupe_key", unique=True, postgresql_where=text("status IN ('pending','running')"), sqlite_where=text("status IN ('pending','running')")),
        CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')", name="ck_jobs_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
