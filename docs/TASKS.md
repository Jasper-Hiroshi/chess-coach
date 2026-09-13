# Implementation backlog

## 已完成的 MVP 基线

- [x] React 多页面工作台、移动端导航与本地预览降级
- [x] FastAPI 公共接口与统一错误结构
- [x] Chess.com 归档/条件请求/重试/PGN 导入和幂等去重
- [x] PostgreSQL 模型与无 Redis 持久化任务
- [x] Stockfish 两遍分析、WDL 严重度和模板解释
- [x] 开局库缓存、训练题、间隔复习、周计划和滚动指标
- [x] PGN/CSV 导出、Docker Compose、基础测试与 13 局夹具
- [x] 首个 Alembic migration、PostgreSQL/SQLite partial unique index 与 CHECK constraints

## 下一轮工程增强

1. **P0：任务租约** — 完成带 `locked_by` 条件的 heartbeat/finish update，增加 worker 崩溃恢复集成测试。
2. **P0：真实引擎验收** — Docker 环境运行 Stockfish 19 金丝雀局面和一盘完整对局性能基准。
3. **P1：事实标签** — 增加漏吃、简单坏交换、发展迟缓、重复走子和王车易位权的可靠测试。
4. **P1：开局下钻** — 让候选着更新 FEN、面包屑和个人路径，不把数据库频率误称为最佳着。
5. **P1：自主复盘持久化** — 保存用户自评、复盘完成状态并纳入执行率。
6. **P2：备份恢复** — 提供数据库导出/恢复脚本和界面状态。
