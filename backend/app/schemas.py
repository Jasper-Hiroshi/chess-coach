from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ChessComImportRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class SyncRequest(BaseModel):
    profile_id: str | None = None


class JobCreated(BaseModel):
    profile_id: str | None = None
    job_id: str
    deduplicated: bool = False


class JobRead(ORMModel):
    id: str
    job_type: str
    status: str
    progress_current: int
    progress_total: int
    current_step: str | None
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def progress(self) -> float:
        return self.progress_current / self.progress_total if self.progress_total else 0.0


class GameSummary(ORMModel):
    id: str
    source_url: str
    played_at: datetime
    time_class: str
    time_control: str
    player_color: str
    player_rating: int | None
    opponent_rating: int | None
    white_name: str
    black_name: str
    result: str
    opening_name: str | None
    eco: str | None
    analysis_status: str
    review_completed: bool
    mistake_count: int = 0


class GameList(BaseModel):
    items: list[GameSummary]
    next_cursor: str | None = None


class MoveView(ORMModel):
    id: str
    ply: int
    side_to_move: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    clock_ms: int | None
    phase: str


class GameDetail(GameSummary):
    raw_pgn: str
    moves: list[MoveView]


class MistakeView(BaseModel):
    id: str
    ply: int
    severity: str
    expected_score_loss: float
    themes: list[str]
    explanation: str
    facts: list[dict[str, Any]]
    best_move_san: str | None
    best_move_uci: str | None
    played_move_san: str
    principal_variations: list[dict[str, Any]]
    training_item_id: str | None = None


class ReviewMove(MoveView):
    expected_score_before: float | None = None
    expected_score_after: float | None = None
    severity: str = "normal"


class GameReview(BaseModel):
    game: GameSummary
    analysis_status: str
    player_color: str
    engine_version: str | None
    moves: list[ReviewMove]
    mistakes: list[MistakeView]


class TrainingItemCreate(BaseModel):
    mistake_id: str


class TrainingItemView(ORMModel):
    id: str
    fen: str
    side_to_move: str
    theme: str
    interval_level: int
    due_at: datetime


class TrainingItemCreated(BaseModel):
    training_item_id: str
    created: bool


class TrainingAttemptCreate(BaseModel):
    training_item_id: str
    move_uci: str = Field(min_length=4, max_length=5)
    used_hint: bool = False
    elapsed_ms: int = Field(default=0, ge=0, le=3_600_000)
    attempt_id: str | None = None


class TrainingAttemptResult(BaseModel):
    correct: bool
    previous_level: int
    new_level: int
    due_at: datetime
    solution_pv: list[str]


class WeeklyPlanView(BaseModel):
    id: str | None = None
    week_start: str
    focus_topics: list[dict[str, Any]]
    activities: list[dict[str, Any]]
    sample_count: int


class ProgressReport(BaseModel):
    time_class: str
    current_rating: int | None
    target_rating: int
    current_window: dict[str, Any]
    baseline_window: dict[str, Any]
    metrics: list[dict[str, Any]]
    trend_available: bool
    sample_message: str
    metric_version: str


class OpeningMoveView(BaseModel):
    uci: str
    san: str
    personal_count: int
    personal_score: float | None
    lichess_count: int | None
    masters_count: int | None
    confidence: Literal["insufficient", "descriptive", "reliable"]
    recommendation: str


class OpeningTreeView(BaseModel):
    fen: str
    color: str
    sample_count: int
    confidence: str
    opening_name: str | None
    moves: list[OpeningMoveView]
    offline_or_stale: bool


class DashboardView(BaseModel):
    username: str | None
    current_rating: int | None
    target_rating: int
    game_count: int
    analysed_count: int
    due_training_count: int
    sync_status: str
    weekly_plan: WeeklyPlanView
    recent_games: list[GameSummary]
    progress: ProgressReport
