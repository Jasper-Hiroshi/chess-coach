import type { Dashboard, GameReview, GameSummary, Job, OpeningTree, ProgressReport, TrainingItem } from "./types";

const API = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  requestId?: string;

  constructor(code: string, message: string, details: Record<string, unknown> = {}, requestId?: string) {
    super(message);
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Request-Id": crypto.randomUUID(), ...init?.headers }
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(payload.code ?? "request_failed", payload.message ?? "请求失败", payload.details, payload.request_id);
  }
  return response.json();
}

export const api = {
  dashboard: () => request<Dashboard>("/dashboard"),
  importChessCom: (username: string) => request<{ profile_id: string; job_id: string }>("/imports/chess-com", { method: "POST", body: JSON.stringify({ username }) }),
  sync: () => request<{ job_id: string }>("/sync", { method: "POST", body: JSON.stringify({}) }),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  games: () => request<{ items: GameSummary[] }>("/games?limit=100"),
  review: (id: string) => request<GameReview>(`/games/${id}/review`),
  analyse: (id: string) => request<{ job_id: string }>(`/games/${id}/analysis`, { method: "POST" }),
  openings: (color = "white") => request<OpeningTree>(`/openings/tree?color=${color}`),
  training: () => request<TrainingItem[]>("/training/queue"),
  attempt: (id: string, move: string, usedHint: boolean, elapsedMs: number) => request<{ correct: boolean; solution_pv: string[]; due_at: string }>("/training/attempts", { method: "POST", body: JSON.stringify({ training_item_id: id, move_uci: move, used_hint: usedHint, elapsed_ms: elapsedMs }) }),
  addTraining: (mistakeId: string) => request<{ training_item_id: string; created: boolean }>("/training/items", { method: "POST", body: JSON.stringify({ mistake_id: mistakeId }) }),
  progress: () => request<ProgressReport>("/progress?time_class=rapid")
};

