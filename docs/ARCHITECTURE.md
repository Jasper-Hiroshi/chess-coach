# Architecture

## System context

```text
Browser ──REST──> FastAPI ─────────> PostgreSQL 18
                    │                    ▲
                    └──analysis_jobs─────┤
                                         │
                           Worker ────────┘
                             ├── Chess.com PubAPI
                             ├── Lichess Opening Explorer
                             └── Stockfish 19 UCI
```

Web 与 API 只监听本机地址。浏览器只向本地 API 发送训练记录；外部请求仅包含公开用户名、公开 PGN 查询和局面 FEN。

## Data flow

1. `POST /imports/chess-com` upsert 单个 profile，并创建带 dedupe key 的 `sync_games` 任务。
2. worker 顺序读取月度归档；每个月在 HTTP 完成后开启短事务，幂等保存 game/move 和归档缓存头。
3. 新的合法标准棋创建 `analyze_game` 任务。失败月份独立记录，不回滚成功月份。
4. 分析 worker 对所有局面做 100k 节点扫描，对候选用户着在同一根局面做 500k 节点复核。
5. 稳定的错误生成 assessment、mistake 和 training item；API 聚合为复盘、周计划和滚动报告。

## Invariants

- PGN 原文永远保留；非法 PGN 记录错误且不进入引擎。
- 局面评价存白方视角 WDL/期望得分；用户视角只在领域计算和输出层转换。
- `position_analyses.cache_key` 包含 FEN、引擎/算法版本、节点数、MultiPV、root moves 和 UCI 选项。
- 严重度阈值固定为 `<.05 / .05–.10 / .10–.20 / >=.20`，将杀变化覆盖为严重失误。
- 个人开局样本 `<5` 不展示胜率，`5–19` 只描述观察，`>=20` 才允许稳定倾向结论。
- 趋势需要最近 20 局；前后比较需要同类共 40 局。
- worker 为 at-least-once；唯一约束与 dedupe key 负责幂等。

## Failure model

- Chess.com 网络错误、429、5xx 可重试；404 用户错误不可重试。
- Lichess 失败时返回已缓存数据，或仅展示个人路径并标记 stale。
- Stockfish 失败由 job retry；不写入半条 assessment。
- 任务 lease 过期可由另一个 worker 重新领取；旧 worker 不得覆盖新结果。

## Security and privacy

- 不实现登录，不对局域网和公网暴露端口。
- 外部主机由适配器常量固定，用户不能提交任意 URL。
- 无远程遥测；数据库和训练记录仅保存在本地卷。

