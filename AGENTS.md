# AI 协作规则

## 架构所有权

- Codex 主代理拥有跨模块契约、数据模型、迁移、集成、最终验收和提交判断。
- 其他 AI 只接收边界明确、接口冻结、可独立验证的任务。
- 任何公共 REST 字段、数据库约束、任务状态或分析阈值变更，必须先更新 `docs/API.md` 或 `docs/ARCHITECTURE.md`，再实现。
- 禁止多个代理同时修改同一文件；并行任务必须声明文件所有权。

## 固定技术决策

- Web：React 19、TypeScript、Vite，使用现有 CSS token，不引入第二套 UI 框架。
- API：FastAPI、Pydantic 2、SQLAlchemy 2；Docker 使用 PostgreSQL 18，本地测试可用 SQLite。
- Worker：PostgreSQL 持久化队列，at-least-once 语义，handler 必须幂等。
- 引擎：Stockfish 19，Threads=1、Hash=256 MB；默认 100k 节点扫描、500k 节点复核。
- 分析指标统一存白方视角；展示和 move loss 时才转换为用户视角。
- 外部 HTTP 与 Stockfish 运算禁止放在数据库事务内。
- 中文解释只能陈述棋盘或 PV 可验证事实，不推测心理和战略意图。

## 推荐任务拆分

| 任务 | 文件所有权 | 前置 | 验收 |
|---|---|---|---|
| Chess.com 导入增强 | `backend/app/integrations/chess_com.py`, `services/ingestion.py` | 模型稳定 | 导入夹具 13 局且二次为 0 新增 |
| Stockfish 标签增强 | `backend/app/services/analysis.py` | 引擎接口稳定 | 金丝雀局面与视角测试通过 |
| PostgreSQL 队列增强 | `backend/app/queue.py`, `worker.py` | 数据模型稳定 | lease、重试、取消、回收测试通过 |
| 开局路径下钻 | `backend/app/api.py` 的 opening 区域、对应前端页面 | API shape 冻结 | 每一步 FEN 路径可前后导航 |
| 复盘体验 | `web/src/App.tsx`, `styles.css` | review API 稳定 | 键盘/窄屏/隐藏答案通过 |
| 测试补齐 | 新增 `backend/tests/*` | 对应功能完成 | 不修改生产逻辑来迎合测试 |

## 强制质量门禁

1. `python -m pytest backend/tests`
2. `npm run build`（`web` 目录）
3. 检查 `/health/live`、`/health/ready`、`/api/v1/dashboard`
4. 用固定 13 局夹具验证导入幂等
5. 复核最终 diff，不做无关重构

