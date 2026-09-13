# 棋迹（Chess Coach）

棋迹是一套本地运行的个人国际象棋复盘与训练系统。它从 Chess.com 导入公开 PGN，使用 Stockfish 分析关键转折，把可靠的失误事实转换为中文解释和间隔复习题，并用同类对局滚动窗口衡量进步。

## 功能

- Chess.com 月度归档增量同步、条件请求、幂等去重和异常月份隔离
- Stockfish 固定节点两遍分析、WDL 期望得分与用户视角严重度
- 棋盘式单局复盘、自主判断门、关键失误与推荐变化
- Lichess 大众库/大师库开局对比及个人样本置信度
- 来自个人实战的训练题、1/3/7/14/30 天复习阶梯
- 每周三个重点、4–6 小时训练配额、20/40 局滚动指标
- PGN 与分析 CSV 导出

## 推荐运行方式

1. 安装 Docker Desktop。
2. 复制 `.env.example` 为 `.env`，把 `CHESS_COM_USER_AGENT` 中的联系邮箱替换为自己的邮箱。
3. 执行：

   ```powershell
   docker compose up --build
   ```

4. 打开 `http://127.0.0.1:5173`，首次启动输入 Chess.com ID 后同步；未连接后端时的预览身份固定为 `demo_player`。

首次 Docker 构建会从官方 `sf_19` 标签编译 Stockfish 19，因此耗时会明显长于后续启动。数据保存在 Docker 卷 `postgres-data` 中。

## 无 Docker 开发

后端默认使用当前目录的 SQLite 数据库，便于本地调试；Docker 环境固定使用 PostgreSQL 18。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

在另一个终端启动 worker（需要本机可执行的 Stockfish）：

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker
```

再启动前端：

```powershell
cd web
npm install
npm run dev
```

## 质量检查

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
cd ..\web
npm run build
```

详细架构、公共接口与协作任务边界见 `docs/` 和根目录 `AGENTS.md`。

## 数据与隐私

- 仓库只包含标记为 `synthetic` 的演示棋局，不包含真实 Chess.com 用户名或真实对局元数据。
- 用户在运行时输入 Chess.com ID；同步后的 PGN、分析和训练记录仅保存在本地数据库中。
- `.env`、`*.db`、Docker 数据卷、虚拟环境与构建产物均被 `.gitignore` 排除，应用不会自动上传这些数据。

## 许可证

项目采用 GPL-3.0-only。Stockfish 19 由 Dockerfile 从官方源码构建；相关源码和许可证地址见 `LICENSE`。

