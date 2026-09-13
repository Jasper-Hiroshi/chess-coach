# Public API v1

所有 JSON 使用 `snake_case`。异步创建返回 HTTP 202 和 `job_id`。错误统一为：

```json
{"code":"machine_code","message":"中文说明","details":{},"request_id":"uuid"}
```

## Import and jobs

- `POST /api/v1/imports/chess-com` — `{username}` → `{profile_id, job_id, deduplicated}`
- `POST /api/v1/sync` — `{profile_id?}` → job
- `GET /api/v1/jobs/{job_id}` — 状态、进度、当前步骤、结果或错误
- `DELETE /api/v1/jobs/{job_id}` — pending 立即取消，running 请求软取消

## Games and review

- `GET /api/v1/games?time_class=&color=&result=&analysis_status=&limit=`
- `GET /api/v1/games/{game_id}`
- `POST /api/v1/games/{game_id}/analysis?force=false`
- `GET /api/v1/games/{game_id}/review`

复盘返回 `game/player_color/engine_version/moves/mistakes`。每个错误包含 ply、严重度、期望得分损失、事实、中文解释、推荐着和训练题 ID。

## Opening, training and progress

- `GET /api/v1/openings/tree?color=white&fen=...`
- `GET /api/v1/training/queue`
- `POST /api/v1/training/items` — `{mistake_id}`，幂等创建
- `POST /api/v1/training/attempts` — `{training_item_id, move_uci, used_hint, elapsed_ms, attempt_id?}`
- `GET /api/v1/plans/current`
- `POST /api/v1/plans/generate`
- `GET /api/v1/progress?time_class=rapid`
- `GET /api/v1/dashboard`

## Export and health

- `GET /api/v1/exports/games.pgn`
- `GET /api/v1/exports/analysis.csv`
- `GET /health/live`
- `GET /health/ready`

运行 API 后，完整且可执行的 OpenAPI 位于 `/docs` 和 `/openapi.json`。

