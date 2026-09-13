export type Severity = "normal" | "inaccuracy" | "mistake" | "blunder";

export interface WeeklyPlan {
  id?: string | null;
  week_start: string;
  focus_topics: Array<{ theme: string; title: string; evidence: string; target_sessions: number }>;
  activities: Array<{ title: string; minutes: number }>;
  sample_count: number;
}

export interface ProgressReport {
  time_class: string;
  current_rating: number | null;
  target_rating: number;
  current_window: { count: number; from?: string; to?: string; blunders_per_100?: number | null; mistakes_per_100?: number | null };
  baseline_window: { count: number; from?: string; to?: string; blunders_per_100?: number | null; mistakes_per_100?: number | null };
  metrics: Array<{ key: string; label: string; current: number | null; baseline: number | null; unit: string; direction: string }>;
  trend_available: boolean;
  sample_message: string;
  metric_version: string;
}

export interface GameSummary {
  id: string;
  source_url: string;
  played_at: string;
  time_class: string;
  time_control: string;
  player_color: "white" | "black";
  player_rating: number | null;
  opponent_rating: number | null;
  white_name: string;
  black_name: string;
  result: string;
  opening_name: string | null;
  eco: string | null;
  analysis_status: string;
  review_completed: boolean;
  mistake_count: number;
}

export interface Dashboard {
  username: string | null;
  current_rating: number | null;
  target_rating: number;
  game_count: number;
  analysed_count: number;
  due_training_count: number;
  sync_status: string;
  weekly_plan: WeeklyPlan;
  recent_games: GameSummary[];
  progress: ProgressReport;
}

export interface ReviewMove {
  id: string;
  ply: number;
  side_to_move: "white" | "black";
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  clock_ms: number | null;
  phase: string;
  expected_score_before: number | null;
  expected_score_after: number | null;
  severity: Severity;
}

export interface MistakeView {
  id: string;
  ply: number;
  severity: Severity;
  expected_score_loss: number;
  themes: string[];
  explanation: string;
  facts: Array<{ label: string; value: string }>;
  best_move_san: string | null;
  best_move_uci: string | null;
  played_move_san: string;
  principal_variations: Array<{ pv?: string[]; expected_score_white?: number }>;
  training_item_id: string | null;
}

export interface GameReview {
  game: GameSummary;
  analysis_status: string;
  player_color: "white" | "black";
  engine_version: string | null;
  moves: ReviewMove[];
  mistakes: MistakeView[];
}

export interface Job {
  id: string;
  job_type: string;
  status: string;
  progress_current: number;
  progress_total: number;
  current_step: string | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingItem {
  id: string;
  fen: string;
  side_to_move: "white" | "black";
  theme: string;
  interval_level: number;
  due_at: string;
}

export interface OpeningMove {
  uci: string;
  san: string;
  personal_count: number;
  personal_score: number | null;
  lichess_count: number | null;
  masters_count: number | null;
  confidence: string;
  recommendation: string;
}

export interface OpeningTree {
  fen: string;
  color: string;
  sample_count: number;
  confidence: string;
  opening_name: string | null;
  moves: OpeningMove[];
  offline_or_stale: boolean;
}

