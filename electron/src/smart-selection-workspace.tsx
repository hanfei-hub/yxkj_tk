import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { User } from "./types";
import * as service from "./api";
import "./smart-selection-workspace.css";

type PipelineTask = Record<string, any>;
type Item = Record<string, unknown>;
type BoardGroup = { keyword_id: number; keyword: string; items: Item[] };

const HOT_SEARCHES = ["家居好物", "夏季防晒", "学生平价好物", "新奇特", "厨房小工具", "户外装备"];
const FLOW_NODES = [
  ["AI 对话挖掘潜力爆品", "根据需求生成适配日本 TikTok 的潜力商品方向。"],
  ["全网数据拓品，摸清市场全貌", "抓取同赛道商品数据，建立价格、款式和热度参考。"],
  ["多维风控过滤，规避运营雷区", "筛除禁运、禁售、侵权和报关受限商品。"],
  ["热销竞品规避，抢占蓝海赛道", "按 EchoTik 销量识别成熟爆款，优先保留低竞争机会。"],
  ["自动生成专业可视化选品报告", "沉淀市场、风险、机会和供应链判断。"],
  ["智能匹配 1688 优质供应链", "评估供应价格、发货效率与稳定性。"],
  ["输出最终精选 10 款优质爆品", "交付候选品和可直接运营的精选商品。"],
] as const;
const STAGE_MAP: Record<string, number> = { created: -1, keyword_generation: 0, supplier_search: 1, price_seed_selection: 1, image_search: 1, product_detail: 1, compliance_filter: 2, blue_ocean_filter: 3, report_generation: 4, supplier_evaluation: 5, final_selection: 6 };

function asItems(value: unknown): Item[] { return Array.isArray(value) ? value as Item[] : []; }
function itemImage(item: Item) { return String(item.image_url || item.supplier_image_url || ""); }
function itemTitle(item: Item) { return String(item.title || item.product_name || item.keyword || "未命名商品"); }
function itemKey(item: Item, index: number) { return String(item.id || item.product_id || `${itemTitle(item)}-${index}`); }

function ProductReel({ items, tick }: { items: Item[]; tick: number }) {
  if (!items.length) return <div className="selection-stage-wait">正在准备商品样本…</div>;
  const width = 94;
  const move = (tick % Math.max(items.length, 1)) * width;
  return <div className="selection-reel"><div className="selection-reel-track" style={{ transform: `translateX(-${move}px)` }}>{[...items, ...items].map((item, index) => <article className="selection-reel-card" key={`${itemKey(item, index)}-${index}`} title={itemTitle(item)}>{itemImage(item) ? <img src={itemImage(item)} loading="lazy" /> : <span>暂无图片</span>}<b>{itemTitle(item)}</b></article>)}</div></div>;
}

function ProductGrid({ items, compact = false }: { items: Item[]; compact?: boolean }) {
  if (!items.length) return <div className="selection-stage-wait">当前阶段暂无可展示商品。</div>;
  return <div className={compact ? "selection-stage-product-grid compact" : "selection-stage-product-grid"}>{items.slice(0, compact ? 8 : 10).map((item, index) => <article className={`selection-stage-product ${item.eliminated ? "eliminated" : ""}`} key={itemKey(item, index)}><div>{itemImage(item) ? <img src={itemImage(item)} loading="lazy" /> : <span>暂无图片</span>}</div><b>{itemTitle(item)}</b><small>{item.eliminated ? "已淘汰" : `销量 ${Number(item.sales_count || 0).toLocaleString()}`}</small></article>)}</div>;
}

function SelectionTimeline({ status, currentStep, keywords, groups, counters, boardItems, reportTask, tick, onExport }: { status: string; currentStep: number; keywords: Item[]; groups: BoardGroup[]; counters: Record<string, number>; boardItems: Item[]; reportTask: PipelineTask | null; tick: number; onExport: () => void }) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [showAllKeywords, setShowAllKeywords] = useState(false);
  const allDone = status === "success";
  const liveGroups = useMemo(() => groups.filter((group) => group.keyword_id >= 0), [groups]);
  const candidates = useMemo(() => groups.find((group) => group.keyword_id === -1)?.items || [], [groups]);
  const finals = useMemo(() => groups.find((group) => group.keyword_id === -2)?.items || [], [groups]);
  const eliminated = useMemo(() => liveGroups.flatMap((group) => group.items).filter((item) => Boolean(item.eliminated)), [liveGroups]);
  const analysis = (reportTask?.ai_report || {}) as Record<string, any>;
  const market = (analysis.market_intro || {}) as Record<string, unknown>;
  const summary = (index: number) => [
    keywords.length ? `${keywords.length} 个方向已生成` : "正在解析需求",
    counters.supplier_candidates ? `${counters.supplier_candidates} 个货源已匹配` : "正在匹配供应链",
    eliminated.length ? `${eliminated.length} 个风险商品已筛除` : "正在风控审核",
    candidates.length ? `${candidates.length} 个蓝海候选品` : "正在识别蓝海机会",
    reportTask ? "精品分析报告已生成" : "正在生成报告",
    liveGroups.length ? "1688 商品可展开查看" : "正在准备货源",
    finals.length ? `${finals.length} 个精选商品已出炉` : "正在精选最终商品",
  ][index];
  const stageBody = (index: number) => {
    if (index === 0) {
      const visible = showAllKeywords ? keywords : keywords.slice(0, 12);
      return keywords.length ? <><div className="selection-keyword-chips">{visible.map((item, keyIndex) => <span key={itemKey(item, keyIndex)}>{String(item.keyword || item.title || "潜力方向")}</span>)}</div>{keywords.length > 12 && <button className="selection-inline-button" onClick={() => setShowAllKeywords((value) => !value)}>{showAllKeywords ? "收起关键词" : `查看全部 ${keywords.length} 个方向`}</button>}</> : <div className="selection-stage-wait">AI 正在拆解需求与日本消费场景…</div>;
    }
    if (index === 1 || index === 5) return liveGroups.length ? <div className="selection-supplier-rows">{liveGroups.slice(0, 12).map((group) => <div key={group.keyword_id} className="selection-supplier-row"><b title={group.keyword}>{group.keyword}</b><ProductReel items={group.items} tick={tick} /></div>)}</div> : <div className="selection-stage-wait">正在匹配优质产业带货源…</div>;
    if (index === 2) return eliminated.length ? <div className="selection-eliminated-list">{eliminated.slice(0, 6).map((item, itemIndex) => <div key={itemKey(item, itemIndex)}><i>×</i><span>{itemTitle(item)}</span><small>已通过风控规则淘汰</small></div>)}</div> : <div className="selection-stage-wait">正在进行禁运、限售与侵权风险筛查…</div>;
    if (index === 3) return <ProductGrid items={candidates.length ? candidates : boardItems.filter((item) => !item.eliminated)} compact />;
    if (index === 4) return reportTask ? <section className="selection-report-preview"><h3>精品分析报告</h3><p>{String(analysis.conclusion || analysis.market_summary || "市场分析已生成，可导出完整报告。")}</p><div><span><b>市场规模</b>{String(market.market_scale || "待进一步验证")}</span><span><b>需求趋势</b>{String(market.demand_trend || "待进一步验证")}</span><span><b>竞争格局</b>{String(market.competition_landscape || "待进一步验证")}</span></div><button className="secondary" onClick={onExport}>导出完整选品报告</button></section> : <div className="selection-stage-wait">正在整理市场机会、风险和用户需求分析…</div>;
    return <ProductGrid items={finals} />;
  };
  if (status === "idle") return <div className="empty-state">任务开始后，这里会按步骤展示动态、商品结果与完整报告。</div>;
  return <div className="selection-timeline">{FLOW_NODES.map(([title], index) => {
    const done = index < currentStep || allDone;
    const active = (index === currentStep && status === "running") || (allDone && index === 6);
    const open = active || Boolean(expanded[index]);
    return <section className={`selection-timeline-step ${done ? "done" : "pending"} ${active ? "active" : ""} ${open ? "open" : ""}`} key={title}><button type="button" className="selection-timeline-toggle" aria-expanded={open} disabled={active} onClick={() => setExpanded((value) => ({ ...value, [index]: !value[index] }))}><span className="selection-step-marker">{done ? "✓" : String(index + 1).padStart(2, "0")}</span><span className="selection-step-heading"><b>{title}</b><small>{summary(index)}</small></span>{!active && <span className="selection-caret">{open ? "收起" : "查看"}</span>}{active && <span className="selection-running">进行中</span>}</button>{open && <div className="selection-timeline-body">{stageBody(index)}</div>}</section>;
  })}</div>;
}

export function SmartSelectionWorkspace({ user, onNotice, onExportReport }: { user: User; onNotice: (message: string) => void; onExportReport: (task: PipelineTask) => Promise<void> }) {
  const [message, setMessage] = useState("");
  const [taskId, setTaskId] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "success" | "failed">("idle");
  const [stage, setStage] = useState("created");
  const [progress, setProgress] = useState(0);
  const [taskMessage, setTaskMessage] = useState("");
  const [groups, setGroups] = useState<BoardGroup[]>([]);
  const [keywords, setKeywords] = useState<Item[]>([]);
  const [boardItems, setBoardItems] = useState<Item[]>([]);
  const [counters, setCounters] = useState<Record<string, number>>({});
  const [logs, setLogs] = useState<Array<{ time: string; text: string }>>([]);
  const [reportTask, setReportTask] = useState<PipelineTask | null>(null);
  const [reelTick, setReelTick] = useState(0);
  const stageRef = useRef("");
  const stageAtRef = useRef(0);
  const currentStep = useMemo(() => STAGE_MAP[stage] ?? Math.min(6, Math.floor(progress / 15)), [stage, progress]);
  const storageKey = `tk_selection_pipeline_task_${user.id || user.username || "current"}`;

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setReelTick((value) => value + 1), 2200);
    return () => window.clearInterval(timer);
  }, []);

  const applyTask = useCallback(async (data: PipelineTask, restoreInput = false) => {
    const nextStage = String(data.stage || "created");
    const elapsed = Date.now() - stageAtRef.current;
    if (stageRef.current && stageRef.current !== nextStage && elapsed < 1000) await new Promise((resolve) => window.setTimeout(resolve, 1000 - elapsed));
    const changed = nextStage !== stageRef.current;
    if (changed) { stageRef.current = nextStage; stageAtRef.current = Date.now(); }
    setStage(nextStage); setProgress(Number(data.progress || 0)); setTaskMessage(String(data.message || "")); setCounters(data.counters || {});
    if (restoreInput && data.input_message) setMessage(String(data.input_message));
    const nextGroups: BoardGroup[] = Array.isArray(data.board_groups) ? [...data.board_groups] : [];
    if (asItems(data.candidate_items).length) nextGroups.push({ keyword_id: -1, keyword: "30 个候选蓝海商品", items: asItems(data.candidate_items) });
    if (asItems(data.final_items).length) nextGroups.push({ keyword_id: -2, keyword: "10 个精选商品", items: asItems(data.final_items) });
    setGroups(nextGroups); setKeywords(asItems(data.keywords)); setBoardItems(asItems(data.board_items));
    if (data.status === "success") setReportTask(data);
    if (changed) setLogs((items) => [...items, { time: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }), text: String(data.message || "任务状态已更新") }].slice(-5));
  }, []);

  useEffect(() => { let disposed = false; void (async () => { try { const stored = Number(localStorage.getItem(storageKey) || 0); const latest = stored ? { task_id: stored } : await service.getLatestSelectionPipelineTask(); if (!latest.task_id || disposed) return; const data = await service.getSelectionPipelineTask(latest.task_id); if (disposed) return; await applyTask(data, true); setStatus(data.status === "success" ? "success" : data.status === "failed" ? "failed" : "running"); if (!["success", "failed"].includes(String(data.status))) setTaskId(Number(latest.task_id)); } catch { /* 无历史任务时保持待开始状态。 */ } })(); return () => { disposed = true; }; }, [applyTask, storageKey]);
  useEffect(() => { if (!taskId) return; const timer = window.setInterval(() => void (async () => { try { const data = await service.getSelectionPipelineTask(taskId); await applyTask(data); if (["success", "failed"].includes(String(data.status))) { window.clearInterval(timer); setTaskId(null); setStatus(data.status); if (data.status === "success") onNotice("选品任务完成，候选品与精选品已自动写入选品库"); } } catch (error) { window.clearInterval(timer); setTaskId(null); setStatus("failed"); onNotice(error instanceof Error ? error.message : "任务查询失败"); } })(), 1500); return () => window.clearInterval(timer); }, [applyTask, onNotice, taskId]);

  const submit = useCallback(async () => { if (!message.trim() || taskId) return; try { setStatus("running"); setStage("created"); setProgress(1); setTaskMessage("正在创建智能选品任务"); setGroups([]); setKeywords([]); setBoardItems([]); setCounters({}); setLogs([]); setReportTask(null); const result = await service.createSelectionPipelineTask(message.trim()); if (!result.task_id) throw new Error("服务未返回任务编号"); localStorage.setItem(storageKey, String(result.task_id)); setTaskId(Number(result.task_id)); } catch (error) { setStatus("failed"); onNotice(error instanceof Error ? error.message : "启动选品任务失败"); } }, [message, onNotice, storageKey, taskId]);
  const exportReport = useCallback(async () => { if (!reportTask) return; try { await onExportReport(reportTask); onNotice("选品报告已下载"); } catch (error) { onNotice(error instanceof Error ? error.message : "报告下载失败"); } }, [onExportReport, onNotice, reportTask]);

  return <section className="smart-selection smart-selection-workspace"><header className="smart-workspace-heading"><div><h2>AI 智能选品</h2><p>输入需求后，实时查看七步筛选和每个商品的供应链结果。</p></div><span className={`smart-status ${status}`}>{status === "running" ? "任务执行中" : status === "success" ? "任务完成" : status === "failed" ? "任务失败" : "等待开始"}</span></header><div className="smart-workspace-grid"><div className="smart-workspace-left"><div className="smart-chat smart-chat-modern"><div className="smart-chat-title"><b>告诉我您想找什么样的产品？</b><small>AI 选品助手</small></div><textarea value={message} maxLength={300} placeholder="输入选品需求，例如：日本 TikTok 夏季防晒蓝海商品" onChange={(event) => setMessage(event.target.value)} disabled={Boolean(taskId)} /><div className="smart-chat-actions"><div className="smart-hot-searches"><b>热门搜索：</b>{HOT_SEARCHES.map((item) => <button key={item} type="button" disabled={Boolean(taskId)} onClick={() => setMessage(item)}>{item}</button>)}</div><div className="smart-controls"><span>{message.length}/300</span><button className="primary" disabled={!message.trim() || Boolean(taskId)} onClick={() => void submit()}>{taskId ? "执行中…" : "智能选品"}</button></div></div>{status !== "idle" && <div className="smart-progress"><div><span>{taskMessage || "正在执行选品流程"}</span><b>{progress}%</b></div><i><em style={{ width: `${progress}%` }} /></i></div>}</div><section className="selection-flow-panel smart-flow-panel"><div className="selection-flow-heading"><div><h2>智能选品流程</h2><p>{status === "idle" ? "点击智能选品后实时查看每一步进度" : taskMessage || FLOW_NODES[Math.max(0, currentStep)]?.[0]}</p></div></div><div className="smart-flow-list">{FLOW_NODES.map(([title, description], index) => <article key={title} className={`smart-flow-step ${index < currentStep || status === "success" ? "done" : index === currentStep && status === "running" ? "active" : ""}`}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{title}</b><small>{description}</small>{index === currentStep && status === "running" && <em>{taskMessage}</em>}</div></article>)}</div></section></div><aside className="task-board-panel smart-workspace-board"><div className="task-board-header"><div><h2>任务结果看板</h2><p>大模型 {counters.keywords || 0} · 1688 {counters.supplier_candidates || 0} · EchoTik {counters.didadog_details || 0}</p></div>{status === "success" && <button className="secondary" onClick={() => void exportReport()}>导出选品报告</button>}</div><div className="task-board-logs">{logs.length ? logs.slice(-3).map((log, index) => <div key={`${log.time}-${index}`} className="task-board-log"><time>{log.time}</time><span>{log.text}</span></div>) : <div className="task-board-log"><span>任务执行后，实时动态会显示在这里。</span></div>}</div><SelectionTimeline status={status} currentStep={currentStep} keywords={keywords} groups={groups} counters={counters} boardItems={boardItems} reportTask={reportTask} tick={reelTick} onExport={() => void exportReport()} /></aside></div></section>;
}
