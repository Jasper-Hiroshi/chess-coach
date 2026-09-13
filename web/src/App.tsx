import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import {
  Activity, AlertTriangle, BarChart3, BookOpen, BrainCircuit, Check, ChevronLeft, ChevronRight,
  CircleHelp, Clock3, CloudOff, Download, Gauge, Home, Library, ListChecks, LoaderCircle, Menu,
  RefreshCw, RotateCcw, Search, Swords, Target, X
} from "lucide-react";
import { api } from "./api";
import { ChessBoard } from "./components/ChessBoard";
import type { Dashboard, GameReview, GameSummary, Job, OpeningTree, ProgressReport, TrainingItem } from "./types";

const startFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const demoDashboard: Dashboard = {
  username: "demo_player", current_rating: 600, target_rating: 900, game_count: 13, analysed_count: 0,
  due_training_count: 0, sync_status: "preview",
  weekly_plan: {
    week_start: new Date().toISOString().slice(0, 10), sample_count: 13,
    focus_topics: [
      { theme: "cct_scan", title: "先检查对方的将军与吃子", evidence: "冷启动基础训练", target_sessions: 5 },
      { theme: "time", title: "10 分钟棋局控制用时", evidence: "冷启动基础训练", target_sessions: 3 },
      { theme: "opening", title: "固定首回合应对", evidence: "样本不足，先建立熟悉度", target_sessions: 2 }
    ],
    activities: [
      { title: "4 局 15+10 实战", minutes: 120 }, { title: "先自评，再看引擎", minutes: 100 },
      { title: "5 次到期训练", minutes: 80 }, { title: "残局 / 开局复习", minutes: 40 }
    ]
  },
  recent_games: [],
  progress: { time_class: "rapid", current_rating: 600, target_rating: 900, current_window: { count: 13 }, baseline_window: { count: 0 }, metrics: [], trend_available: false, sample_message: "目前只有 13 局同类对局；至少 40 局才进行前后窗口比较。", metric_version: "metrics-v1" }
};

const severityLabels = { normal: "正常", inaccuracy: "不精确", mistake: "错误", blunder: "严重失误" } as const;
const themeLabels: Record<string, string> = {
  allowed_mate: "避免一步被杀", missed_mate: "寻找强制将杀", hung_piece: "子力安全",
  immediate_material_loss: "对方的吃子", early_queen_move: "开局发展", time_trouble: "时间管理", calculation: "局面计算"
};

function useAsync<T>(load: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = () => {
    setLoading(true);
    load().then(setData).catch(setError).finally(() => setLoading(false));
  };
  useEffect(refresh, dependencies); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, refresh };
}

function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigation = [
    { to: "/", label: "总览", icon: Home }, { to: "/games", label: "对局", icon: Swords },
    { to: "/training", label: "训练", icon: BrainCircuit }, { to: "/openings", label: "开局树", icon: Library },
    { to: "/progress", label: "进步", icon: BarChart3 }
  ];
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="棋迹首页"><span className="brand-mark">♞</span><span>棋迹</span></Link>
        <nav aria-label="主导航">
          {navigation.map(({ to, label }) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? "active" : ""}>{label}</NavLink>)}
        </nav>
        <span className="local-badge"><i />本地运行</span>
        <button className="mobile-menu" onClick={() => setMobileOpen((value) => !value)} aria-label="打开导航"><Menu /></button>
      </header>
      {mobileOpen && <div className="mobile-drawer">{navigation.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setMobileOpen(false)}><Icon size={18} />{label}</NavLink>)}</div>}
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/games" element={<GamesPage />} />
        <Route path="/games/:gameId/review" element={<ReviewPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/openings" element={<OpeningsPage />} />
        <Route path="/progress" element={<ProgressPage />} />
      </Routes>
      <div className="bottom-nav">{navigation.slice(0, 4).map(({ to, label, icon: Icon }) => <NavLink key={to} to={to}><Icon size={20} /><span>{label}</span></NavLink>)}</div>
    </div>
  );
}

function OfflineNotice({ error }: { error: Error | null }) {
  if (!error) return null;
  return <div className="notice offline" role="status"><CloudOff size={17} /><span>后端尚未连接，当前显示预览数据。启动 API 后会自动读取本地数据库。</span></div>;
}

function DashboardPage() {
  const { data, error, loading, refresh } = useAsync(api.dashboard, []);
  const dashboard = data ?? demoDashboard;
  const [username, setUsername] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState("");
  const activeUsername = data?.username ?? username;

  const startSync = async () => {
    setMessage("");
    try {
      const created = data?.username ? await api.sync() : await api.importChessCom(username.trim());
      const poll = async () => {
        const next = await api.job(created.job_id);
        setJob(next);
        if (["pending", "running"].includes(next.status)) window.setTimeout(poll, 1500);
        else { setMessage(next.status === "succeeded" ? "同步完成" : next.error_message ?? "同步未完成"); refresh(); }
      };
      await poll();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "同步失败");
    }
  };

  useEffect(() => {
    const context = (document as Document & { modelContext?: { registerTool: (tool: unknown, options?: unknown) => unknown } }).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(context.registerTool({
        name: "sync_chess_com_games", title: "同步 Chess.com 对局",
        description: "使用页面中配置的 Chess.com ID 同步公开对局，并更新可见仪表盘。",
        inputSchema: { type: "object", properties: { username: { type: "string" } }, additionalProperties: false },
        annotations: { readOnlyHint: false, untrustedContentHint: true },
        execute: async (input: unknown) => {
          const value = (input as { username?: string })?.username?.trim();
          if (value) setUsername(value);
          const created = data?.username ? await api.sync() : await api.importChessCom(value || username);
          return { job_id: created.job_id, status: "queued" };
        }
      }, { signal: lifecycle.signal }));
    } catch { /* unsupported experimental API */ }
    return () => lifecycle.abort();
  }, [data?.username, username]);

  return (
    <main>
      <OfflineNotice error={error} />
      <section className="control-deck">
        <div><p className="eyebrow">本周训练周期 · {dashboard.weekly_plan.week_start}</p><h1>把每盘棋，变成下一盘的优势。</h1><p className="intro">先减少直接丢子，再扩充开局库。系统只根据足够样本调整方向。</p></div>
        <div className="sync-panel">
          <label htmlFor="username">Chess.com ID</label>
          <div className="sync-row"><input id="username" value={activeUsername} placeholder="输入你的 Chess.com ID" onChange={(event) => setUsername(event.target.value)} disabled={Boolean(data?.username)} autoComplete="username" /><button onClick={startSync} disabled={!activeUsername.trim() || job?.status === "running"}><RefreshCw size={17} className={job?.status === "running" ? "spin" : ""} />{job?.status === "running" ? "正在同步" : "同步新对局"}</button></div>
          <p aria-live="polite">{job?.current_step ?? message ?? `账号：${dashboard.username ?? "尚未连接"}`}</p>
          {job && job.progress_total > 0 && <div className="progress-track"><i style={{ width: `${Math.round(job.progress_current / job.progress_total * 100)}%` }} /></div>}
        </div>
      </section>
      <section className="metric-grid" aria-label="训练概览">
        <Metric icon={Swords} label="Rapid 等级分" value={String(dashboard.current_rating ?? "—")} detail={`目标区间 ${dashboard.target_rating - 100}–${dashboard.target_rating + 100}`} primary />
        <Metric icon={Activity} label="已导入对局" value={String(dashboard.game_count)} detail={dashboard.progress.sample_message} />
        <Metric icon={BrainCircuit} label="已完成分析" value={`${dashboard.analysed_count} / ${dashboard.game_count}`} detail={`${dashboard.due_training_count} 道训练题今日到期`} />
        <Metric icon={Clock3} label="证据置信度" value={dashboard.game_count < 20 ? "不足" : dashboard.game_count < 40 ? "观察中" : "可比较"} detail="不会用少量胜负做开局结论" evidence />
      </section>
      <section className="dashboard-grid">
        <article className="panel focus-panel">
          <div className="panel-heading"><div><p className="eyebrow">由实战生成</p><h2>本周只练三件事</h2></div><span>按收益排序</span></div>
          <div className="focus-list">{dashboard.weekly_plan.focus_topics.slice(0, 3).map((item, index) => <Link className="focus-item" to="/training" key={item.theme}><span className={`rank ${index === 0 ? "critical" : index === 1 ? "warning" : "steady"}`}>{String(index + 1).padStart(2, "0")}</span><span><b>{item.title}</b><small>{item.evidence} · 计划 {item.target_sessions} 次</small></span><ChevronRight size={19} /></Link>)}</div>
        </article>
        <article className="panel plan-panel">
          <div className="panel-heading"><div><p className="eyebrow">4–6 小时 / 周</p><h2>训练配额</h2></div><BookOpen size={20} /></div>
          {dashboard.weekly_plan.activities.map((item) => <div className="plan-row" key={item.title}><span>{item.title}</span><b>{formatMinutes(item.minutes)}</b></div>)}
          <Link className="start-button" to="/training">开始今日训练 <ChevronRight size={18} /></Link>
        </article>
      </section>
      {dashboard.recent_games.length > 0 && <RecentGames games={dashboard.recent_games} />}
      {loading && <div className="loading-line"><LoaderCircle className="spin" />读取本地数据</div>}
    </main>
  );
}

function Metric({ icon: Icon, label, value, detail, primary, evidence }: { icon: typeof Swords; label: string; value: string; detail: string; primary?: boolean; evidence?: boolean }) {
  return <article className={`metric ${primary ? "primary" : ""}`}><div className="metric-icon"><Icon size={20} /></div><span>{label}</span><strong className={evidence ? "evidence" : ""}>{value}</strong><small>{detail}</small></article>;
}

function RecentGames({ games }: { games: GameSummary[] }) {
  return <section className="panel recent-section"><div className="panel-heading"><div><p className="eyebrow">最近实战</p><h2>继续复盘</h2></div><Link to="/games">查看全部</Link></div><div className="game-list compact">{games.map((game) => <GameRow game={game} key={game.id} />)}</div></section>;
}

function GamesPage() {
  const { data, error, loading, refresh } = useAsync(api.games, []);
  const [query, setQuery] = useState("");
  const games = (data?.items ?? []).filter((game) => `${game.white_name} ${game.black_name} ${game.opening_name}`.toLowerCase().includes(query.toLowerCase()));
  return <main className="page-main"><PageHeading eyebrow="个人棋谱" title="对局" detail="先自己判断关键转折，再打开引擎分析。" action={<button className="secondary-button" onClick={refresh}><RefreshCw size={16} />刷新</button>} /><OfflineNotice error={error} /><div className="toolbar"><label className="search-field"><Search size={17} /><input placeholder="搜索对手或开局" value={query} onChange={(event) => setQuery(event.target.value)} /></label><a className="secondary-button" href="/api/v1/exports/games.pgn"><Download size={16} />导出 PGN</a></div>{loading ? <Loading /> : games.length ? <div className="panel game-list">{games.map((game) => <GameRow game={game} key={game.id} />)}</div> : <EmptyState icon={Swords} title="还没有可展示的对局" detail="在总览页连接 Chess.com 后，公开对局会出现在这里。" link="/" action="返回总览" />}</main>;
}

function GameRow({ game }: { game: GameSummary }) {
  const opponent = game.player_color === "white" ? game.black_name : game.white_name;
  const won = (game.player_color === "white" && game.result === "1-0") || (game.player_color === "black" && game.result === "0-1");
  const result = game.result === "1/2-1/2" ? "和" : won ? "胜" : "负";
  return <Link className="game-row" to={`/games/${game.id}/review`}><span className={`result-chip result-${result}`}>{result}</span><span><b>{opponent}</b><small>{new Date(game.played_at).toLocaleDateString("zh-CN")} · {game.time_control}</small></span><span className="opening-cell">{game.opening_name || "未命名开局"}<small>{game.eco || "—"}</small></span><span className="mistake-cell"><b>{game.mistake_count}</b><small>关键错误</small></span><span className={`status-text ${game.analysis_status}`}>{statusText(game.analysis_status)}</span><ChevronRight size={18} /></Link>;
}

function ReviewPage() {
  const { gameId = "" } = useParams();
  const navigate = useNavigate();
  const { data: review, error, loading, refresh } = useAsync(() => api.review(gameId), [gameId]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [selfNote, setSelfNote] = useState("");
  const [analysisMessage, setAnalysisMessage] = useState("");
  const move = review?.moves[index - 1];
  const fen = index === 0 ? (review?.moves[0]?.fen_before ?? startFen) : (move?.fen_after ?? startFen);
  const activeMistake = review?.mistakes.find((item) => item.ply === move?.ply);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(review?.moves.length ?? 0, value + 1));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [review?.moves.length]);

  const startAnalysis = async () => {
    try { const created = await api.analyse(gameId); setAnalysisMessage(`分析任务已创建：${created.job_id.slice(0, 8)}`); refresh(); }
    catch (cause) { setAnalysisMessage(cause instanceof Error ? cause.message : "无法创建分析"); }
  };
  if (loading) return <main className="page-main"><Loading /></main>;
  if (!review) return <main className="page-main"><OfflineNotice error={error} /><EmptyState icon={AlertTriangle} title="无法打开这盘棋" detail="请确认后端正在运行，并从对局列表重新进入。" link="/games" action="返回对局" /></main>;

  return <main className="review-main"><div className="review-header"><button className="icon-button" onClick={() => navigate("/games")}><ChevronLeft /></button><div><p>{new Date(review.game.played_at).toLocaleString("zh-CN")} · {review.game.time_control}</p><h1>{review.game.white_name} <span>vs</span> {review.game.black_name}</h1></div><div className="review-status"><span>{review.game.opening_name || "未命名开局"}</span><b>{review.engine_version || statusText(review.analysis_status)}</b></div></div>
    {!revealed && <section className="self-review panel"><div><p className="eyebrow">先形成自己的判断</p><h2>这盘棋的转折点在哪里？</h2><p>先写下一句话，再查看引擎。这样能训练你的局面判断，而不只是阅读答案。</p></div><textarea value={selfNote} onChange={(event) => setSelfNote(event.target.value)} placeholder="例如：我觉得第 12 回合后王变得不安全……" /><button className="start-button" onClick={() => setRevealed(true)}>查看引擎分析</button><button className="text-button" onClick={() => setRevealed(true)}>跳过自主复盘</button></section>}
    <section className={`review-workspace ${revealed ? "" : "masked"}`}>
      <div className="board-column"><div className="board-player"><span>{review.player_color === "black" ? review.game.white_name : review.game.black_name}</span><b>{formatClock(move?.clock_ms ?? null)}</b></div><ChessBoard fen={fen} flipped={review.player_color === "black"} /><div className="board-player current"><span>{review.player_color === "white" ? review.game.white_name : review.game.black_name}</span><b>{review.game.player_rating ?? "—"}</b></div><div className="board-controls"><button onClick={() => setIndex(0)}><RotateCcw size={17} /></button><button onClick={() => setIndex((value) => Math.max(0, value - 1))}><ChevronLeft /></button><span>{index} / {review.moves.length}</span><button onClick={() => setIndex((value) => Math.min(review.moves.length, value + 1))}><ChevronRight /></button></div></div>
      <div className="moves-column panel"><div className="eval-summary"><span>用户视角期望得分</span><b>{move?.expected_score_after != null ? `${Math.round(move.expected_score_after * 100)}%` : "等待分析"}</b></div><div className="move-grid">{Array.from({ length: Math.ceil(review.moves.length / 2) }).map((_, turn) => <div className="move-turn" key={turn}><span>{turn + 1}.</span>{[review.moves[turn * 2], review.moves[turn * 2 + 1]].map((item) => item && <button key={item.ply} className={`${index === item.ply ? "current" : ""} severity-${item.severity}`} onClick={() => setIndex(item.ply)}>{item.san}</button>)}</div>)}</div></div>
      <div className="insight-column panel">{review.analysis_status !== "complete" ? <div className="analysis-empty"><Gauge size={36} /><h2>这盘棋还没有完成分析</h2><p>你仍可浏览棋谱；Stockfish 完成后会显示关键失误和推荐变化。</p><button className="start-button" onClick={startAnalysis}>开始分析</button><small aria-live="polite">{analysisMessage}</small></div> : activeMistake ? <MistakeCard mistake={activeMistake} /> : <div className="analysis-empty"><Check size={36} /><h2>{move ? "当前着没有关键问题" : "选择一步棋"}</h2><p>{move ? "继续查看前后着，重点关注带颜色标记的着法。" : `本局共识别 ${review.mistakes.length} 个关键改进点。`}</p></div>}</div>
    </section>
  </main>;
}

function MistakeCard({ mistake }: { mistake: GameReview["mistakes"][number] }) {
  const [trainingId, setTrainingId] = useState(mistake.training_item_id);
  const [message, setMessage] = useState("");

  const add = async () => { try { const result = await api.addTraining(mistake.id); setTrainingId(result.training_item_id); setMessage("已加入复习队列"); } catch (cause) { setMessage(cause instanceof Error ? cause.message : "加入失败"); } };
  return <div className="mistake-card"><span className={`severity-badge ${mistake.severity}`}>{severityLabels[mistake.severity]}</span><p className="eyebrow">第 {(mistake.ply + 1) >> 1} 回合 · {themeLabels[mistake.themes[0]] || "局面计算"}</p><h2>{mistake.played_move_san} 之后需要重新检查</h2><p className="explanation">{mistake.explanation}</p><div className="comparison"><div><small>实战</small><b>{mistake.played_move_san}</b></div><ChevronRight /><div className="recommended"><small>建议比较</small><b>{mistake.best_move_san || mistake.best_move_uci || "—"}</b></div></div><p className="loss-line">期望得分下降约 {Math.round(mistake.expected_score_loss * 100)}%</p><button className="start-button" disabled={Boolean(trainingId)} onClick={add}>{trainingId ? "已加入训练" : "加入训练队列"}</button><small aria-live="polite">{message}</small></div>;
}

function OpeningsPage() {
  const [color, setColor] = useState("white");
  const { data, error, loading } = useAsync<OpeningTree>(() => api.openings(color), [color]);
  return <main className="page-main"><PageHeading eyebrow="个人开局树" title="先稳定，再扩充" detail="数据库频率只是参考；样本量和引擎安全性优先。" /><div className="segmented"><button className={color === "white" ? "active" : ""} onClick={() => setColor("white")}>执白</button><button className={color === "black" ? "active" : ""} onClick={() => setColor("black")}>执黑</button></div><OfflineNotice error={error} />{loading ? <Loading /> : data ? <section className="opening-layout"><div><ChessBoard fen={data.fen} flipped={color === "black"} /><div className="sample-card"><CircleHelp size={18} /><span><b>{confidenceText(data.confidence)}</b>{data.sample_count} 次个人样本{data.offline_or_stale && " · 大数据库暂不可用"}</span></div></div><div className="panel opening-table"><div className="panel-heading"><div><p className="eyebrow">{data.opening_name || "初始局面"}</p><h2>候选着法</h2></div></div>{data.moves.map((move) => <div className="opening-row" key={move.uci}><b>{move.san}</b><span>{move.personal_count} 次个人使用</span><span>{move.lichess_count?.toLocaleString() ?? "—"} 大众样本</span><span>{move.masters_count?.toLocaleString() ?? "—"} 大师样本</span><small className={`confidence ${move.confidence}`}>{confidenceText(move.confidence)}</small></div>)}</div></section> : <EmptyState icon={Library} title="开局树等待第一批对局" detail="导入后会比较个人路线、大众库与大师库。" link="/" action="导入对局" />}</main>;
}

function TrainingPage() {
  const { data, error, loading, refresh } = useAsync(api.training, []);
  const [index, setIndex] = useState(0);
  const [candidate, setCandidate] = useState("");
  const [result, setResult] = useState<{ correct: boolean; solution_pv: string[]; due_at: string } | null>(null);
  const [hint, setHint] = useState(false);
  const started = useMemo(() => Date.now(), [index]);
  const item: TrainingItem | undefined = data?.[index];
  const submit = async () => { if (!item || !candidate) return; try { setResult(await api.attempt(item.id, candidate, hint, Date.now() - started)); } catch { setResult({ correct: false, solution_pv: [], due_at: new Date().toISOString() }); } };
  const next = () => { setIndex((value) => value + 1); setCandidate(""); setResult(null); setHint(false); refresh(); };
  return <main className="page-main training-main"><PageHeading eyebrow="间隔复习" title="今日训练" detail="每次只解决一个来自你实战的局面。" /><OfflineNotice error={error} />{loading ? <Loading /> : item ? <section className="training-layout"><div><ChessBoard fen={item.fen} flipped={item.side_to_move === "black"} interactive={!result} onMove={setCandidate} /></div><article className="panel training-card"><span className="queue-count">{index + 1} / {data?.length}</span><p className="eyebrow">{themeLabels[item.theme] || item.theme}</p><h2>轮到{item.side_to_move === "white" ? "白方" : "黑方"}，请找出更好的着法</h2><p>点击起点和终点完成一步棋。答案提交前不会显示引擎评价。</p>{hint && <div className="hint"><CircleHelp size={17} />提示主题：{themeLabels[item.theme] || "寻找强制着"}</div>}<div className="candidate"><span>你的选择</span><b>{candidate || "尚未走子"}</b></div>{result ? <div className={`attempt-result ${result.correct ? "correct" : "wrong"}`}>{result.correct ? <Check /> : <X />}<div><b>{result.correct ? "正确" : "这一步还可以改进"}</b><small>参考变化：{result.solution_pv.join(" ") || "暂无"}</small></div></div> : <><button className="start-button" disabled={!candidate} onClick={submit}>提交着法</button><button className="text-button" onClick={() => setHint(true)}>给我一个提示</button></>}{result && <button className="start-button" onClick={next}>下一题</button>}</article></section> : <EmptyState icon={ListChecks} title="今天的复习已完成" detail="完成新对局复盘后，关键局面会自动进入这里。" link="/games" action="复盘一局" />}</main>;
}

function ProgressPage() {
  const { data, error, loading } = useAsync<ProgressReport>(api.progress, []);
  const report = data ?? demoDashboard.progress;
  return <main className="page-main"><PageHeading eyebrow="同类对局滚动窗口" title="进步报告" detail="等级分、错误率和训练执行率分开呈现，不制造单一因果结论。" action={<a className="secondary-button" href="/api/v1/exports/analysis.csv"><Download size={16} />导出分析</a>} /><OfflineNotice error={error} />{loading && !data ? <Loading /> : <><section className="progress-hero panel"><div><span>Rapid 当前等级分</span><strong>{report.current_rating ?? "—"}</strong><small>目标 {report.target_rating}</small></div><div className="rating-track"><i style={{ width: `${Math.min(100, (report.current_rating ?? 0) / report.target_rating * 100)}%` }} /></div><p>{report.sample_message}</p></section><section className="progress-metrics">{report.metrics.length ? report.metrics.map((metric) => <article className="panel" key={metric.key}><span>{metric.label}</span><strong>{metric.current ?? "—"}<small>{metric.unit}</small></strong><p>{report.trend_available && metric.baseline != null ? `此前窗口：${metric.baseline}${metric.unit}` : "等待足够样本后比较"}</p></article>) : <article className="panel sample-placeholder"><Target size={26} /><h2>正在建立第一条错误率基线</h2><p>完成引擎分析后，这里会显示每 100 手的严重失误和关键错误。</p></article>}</section><ProgressBars report={report} /></>}</main>;
}

function ProgressBars({ report }: { report: ProgressReport }) {
  return <section className="panel comparison-panel"><div className="panel-heading"><div><p className="eyebrow">样本完整度</p><h2>滚动窗口</h2></div></div><div className="window-row"><span>当前窗口</span><div><i style={{ width: `${Math.min(100, report.current_window.count / 20 * 100)}%` }} /></div><b>{report.current_window.count} / 20</b></div><div className="window-row"><span>对照窗口</span><div><i style={{ width: `${Math.min(100, report.baseline_window.count / 20 * 100)}%` }} /></div><b>{report.baseline_window.count} / 20</b></div></section>;
}

function PageHeading({ eyebrow, title, detail, action }: { eyebrow: string; title: string; detail: string; action?: React.ReactNode }) {
  return <header className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{detail}</p></div>{action}</header>;
}

function EmptyState({ icon: Icon, title, detail, link, action }: { icon: typeof Swords; title: string; detail: string; link: string; action: string }) {
  return <section className="panel empty-state"><Icon size={40} /><h2>{title}</h2><p>{detail}</p><Link className="start-button" to={link}>{action}<ChevronRight size={18} /></Link></section>;
}

function Loading() { return <div className="loading-line"><LoaderCircle className="spin" />读取本地数据</div>; }
function formatMinutes(minutes: number) { return minutes >= 60 ? `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes}m`; }
function formatClock(value: number | null) { if (value == null) return "—"; const seconds = Math.floor(value / 1000); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`; }
function statusText(value: string) { return ({ not_queued: "未分析", queued: "等待分析", running: "分析中", complete: "已分析", failed: "分析失败", succeeded: "已完成", pending: "等待中" } as Record<string, string>)[value] ?? value; }
function confidenceText(value: string) { return ({ insufficient: "证据不足", descriptive: "观察中", reliable: "样本可靠" } as Record<string, string>)[value] ?? value; }

export function App() { return <AppShell />; }

