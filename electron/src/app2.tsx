import React, { useEffect, useMemo, useRef, useState } from "react";
import type { Product, Role, User, VideoProject } from "./types";
import * as service from "./api";
import "./migrated.css";

type Page = "studio" | "library" | "rank" | "favorites" | "teacher" | "dashboard" | "store" | "video" | "profile" | "about" | "admin";
const menus: Array<{ id: Page; label: string; icon: string; roles: Role[] }> = [
  { id: "studio", label: "智能选品", icon: "⌂", roles: ["admin", "teacher", "student"] },
  { id: "library", label: "选品库", icon: "▣", roles: ["admin", "student"] },
  { id: "rank", label: "新品榜单", icon: "♜", roles: ["admin", "teacher", "student"] },
  { id: "favorites", label: "采集箱", icon: "☆", roles: ["admin", "student"] },
  { id: "teacher", label: "教师看板", icon: "▤", roles: ["admin", "teacher"] },
  { id: "dashboard", label: "数据看板", icon: "◔", roles: ["admin", "teacher"] },
  { id: "store", label: "店铺管理", icon: "▥", roles: ["admin", "teacher", "student"] },
  { id: "video", label: "视频生成", icon: "▶", roles: ["admin", "teacher", "student"] },
  { id: "profile", label: "个人中心", icon: "⚙", roles: ["admin", "teacher", "student"] },
  { id: "about", label: "关于益行", icon: "ⓘ", roles: ["admin", "teacher", "student"] },
  { id: "admin", label: "系统管理", icon: "▦", roles: ["admin"] },
];
function title(p: Product) { return p.title || p.derived_title || "未命名商品"; }
function picture(p: Product) { const snapshot = p.product_snapshot || {}; return p.image_url || p.supplier_image_url || String(snapshot.image_url || snapshot.supplier_image_url || snapshot.pic_url || ""); }
function supplierUrl(p: Product) { const snapshot = p.product_snapshot || {}; return p.supplier_source_url || String(snapshot.supplier_source_url || snapshot.source_url || snapshot.detail_url || (snapshot.supplier_product_id ? `https://detail.1688.com/offer/${snapshot.supplier_product_id}.html` : "")); }
const DEFAULT_REGIONS = [{ region_name: "中国", region_code: "CN" }, { region_name: "美国", region_code: "US" }, { region_name: "日本", region_code: "JP" }, { region_name: "泰国", region_code: "TH" }, { region_name: "越南", region_code: "VN" }, { region_name: "马来西亚", region_code: "MY" }, { region_name: "菲律宾", region_code: "PH" }, { region_name: "新加坡", region_code: "SG" }];
const CATEGORY_LABELS: Record<string, string> = { "Beauty & Personal Care": "美妆个护", "Womenswear & Underwear": "女装与女士内衣", Health: "保健", "Fashion Accessories": "时尚配件", "Sports & Outdoor": "运动与户外", "Phones & Electronics": "手机与数码", "Home Supplies": "居家日用", "Food & Beverage": "食品饮料", "Automotive & Motorcycle": "汽车与摩托车", "Menswear & Underwear": "男装与男士内衣", Collectibles: "收藏品", "Toys & Hobbies": "玩具和爱好" };
function categoryLabel(value?: string) { const text = String(value || "").trim(); if (!text) return "未分类"; return text.split(/\s*\/\s*/).map((part) => CATEGORY_LABELS[part.trim()] || part.trim()).join(" / "); }
function money(p: Product) { const n = Number(p.price ?? p.supplier_price ?? 0); const currency = String(p.currency || "").toUpperCase(); const symbol = ["CNY", "RMB", "YUAN"].includes(currency) || p.region === "CN" ? "¥" : currency === "JPY" || p.region === "JP" ? "円" : "$"; return `${symbol}${n.toFixed(2)}`; }
function pid(p: Product) { return p.id ?? p.source_product_id ?? title(p); }

function Login({ done }: { done: (u: User) => void }) { const [mode, setMode] = useState<"account" | "phone">("account"); const [account, setAccount] = useState(""); const [password, setPassword] = useState(""); const [phone, setPhone] = useState(""); const [code, setCode] = useState(""); const [error, setError] = useState(""); const [sending, setSending] = useState(false); const [seconds, setSeconds] = useState(0); async function sendCode() { if (!phone.trim()) { setError("请输入手机号"); return; } setSending(true); setError(""); try { await service.smsSendCode(phone.trim()); setSeconds(60); const timer = window.setInterval(() => setSeconds((value) => { if (value <= 1) { window.clearInterval(timer); return 0; } return value - 1; }), 1000); } catch (x) { setError(x instanceof Error ? x.message : "验证码发送失败"); } finally { setSending(false); } } async function submit(event: React.FormEvent) { event.preventDefault(); setError(""); try { done(mode === "account" ? await service.login(account, password) : await service.smsLogin(phone.trim(), code.trim())); } catch (x) { setError(x instanceof Error ? x.message : "登录失败"); } } return <div className="login-page"><div className="login-visual"><div className="brand-mark large">TK</div><h1>益行跨境 AI 平台</h1><p>TikTok 日本市场智能选品工作台</p></div><form className="login-card" onSubmit={submit}><h2>欢迎回来</h2><div className="login-tabs"><button type="button" className={mode === "phone" ? "active" : ""} onClick={() => { setMode("phone"); setError(""); }}>手机验证码登录</button><button type="button" className={mode === "account" ? "active" : ""} onClick={() => { setMode("account"); setError(""); }}>账号密码登录</button></div>{mode === "account" ? <><label>账号<input value={account} onChange={(e) => setAccount(e.target.value)} required /></label><label>密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label></> : <><label>手机号<input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="请输入手机号" required /></label><label>验证码<div className="code-input"><input value={code} onChange={(e) => setCode(e.target.value)} placeholder="请输入短信验证码" required /><button type="button" onClick={() => void sendCode()} disabled={sending || seconds > 0}>{seconds ? `${seconds}s 后重发` : sending ? "发送中..." : "获取验证码"}</button></div></label></>}{error && <div className="error">{error}</div>}<button className="primary">登录</button><small className="login-tip">手机号首次登录会自动创建学生账号</small></form></div>; }

function Products({ page, rows, onSelect, selected, onCollect }: { page: Page; rows: Product[]; onSelect: (p: Product) => void; selected: Product | null; onCollect: (p: Product) => void }) { return <div className="workspace"><section className="products"><div className="section-heading"><div><h2>{page === "library" ? "选品库" : page === "favorites" ? "采集箱" : "新品榜单"}</h2><p>{rows.length} 个商品</p></div></div><div className="product-grid">{rows.map((p) => <article className={selected && pid(selected) === pid(p) ? "product selected" : "product"} key={String(pid(p))} onClick={() => onSelect(p)}><div className="image-wrap">{picture(p) ? <img src={picture(p)} loading="lazy" /> : <div className="image-empty">暂无图片</div>}</div><h3>{title(p)}</h3><div className="product-tag">{p.source_type || p.category || "商品"}</div><div className="product-meta"><strong>{money(p)}</strong><span>销量 {Number(p.sales_count ?? p.supplier_sales_count ?? 0).toLocaleString()}</span></div><button onClick={(e) => { e.stopPropagation(); onCollect(p); }}>加入采集箱</button></article>)}</div>{!rows.length && <div className="empty-state">暂无数据</div>}</section><aside className="report"><h2>选品分析报告</h2>{selected ? <><div className="report-product">{picture(selected) ? <img src={picture(selected)} /> : <div className="image-empty">暂无图片</div>}<div><h3>{title(selected)}</h3><strong>{money(selected)}</strong><p>请从详情页查看完整分析</p></div></div><button className="primary full" onClick={() => onCollect(selected)}>加入采集箱</button></> : <div className="empty-state">请选择商品</div>}</aside></div>; }

function Teacher({ notice }: { notice: (s: string) => void }) { const [sources, setSources] = useState<Product[]>([]); const [source, setSource] = useState<Product | null>(null); const [derived, setDerived] = useState<Product[]>([]); useEffect(() => { service.getTeacherProducts().then((list) => { setSources(list); setSource(list[0] || null); }).catch((e) => notice(e instanceof Error ? e.message : "读取教师看板失败")); }, []); useEffect(() => { if (source) service.getTeacherDerived(pid(source)).then(setDerived).catch((e) => notice(e instanceof Error ? e.message : "读取衍生品失败")); }, [source]); async function approve(p: Product) { try { await service.approveDerived(pid(p)); setDerived((rows) => rows.filter((x) => pid(x) !== pid(p))); notice("已通过审核"); } catch (e) { notice(e instanceof Error ? e.message : "审核失败"); } } async function reject(p: Product) { try { await service.rejectDerived(pid(p), [], "教师审核拒绝"); setDerived((rows) => rows.filter((x) => pid(x) !== pid(p))); notice("已拒绝"); } catch (e) { notice(e instanceof Error ? e.message : "拒绝失败"); } } return <section className="teacher-workspace"><div className="teacher-sources"><h2>教师看板</h2><p>选择原商品查看衍生品</p><div className="source-grid">{sources.map((p) => <button className={source && pid(source) === pid(p) ? "source-card active" : "source-card"} key={String(pid(p))} onClick={() => setSource(p)}>{picture(p) ? <img src={picture(p)} /> : <span className="image-empty">暂无图片</span>}<b>{title(p)}</b><small>{p.derived_count ?? 0} 个衍生品</small></button>)}</div></div><div className="review-list"><h2>衍生品审核</h2>{derived.map((p) => <article className="review-card" key={String(pid(p))}><div className="review-head">{picture(p) ? <img src={picture(p)} /> : <div className="image-empty">暂无图片</div>}<div><h3>{title(p)}</h3><span>{money(p)}</span></div><div className="review-actions"><button className="success" onClick={() => approve(p)}>通过</button><button className="danger" onClick={() => reject(p)}>拒绝</button></div></div></article>)}{!derived.length && <div className="empty-state">暂无待审核衍生品</div>}</div></section>; }

function Admin({ notice }: { notice: (s: string) => void }) { const [tab, setTab] = useState("users"); const [rows, setRows] = useState<unknown[]>([]); useEffect(() => { const task = tab === "users" ? service.getUsers() : tab === "models" ? service.getModelConfigs() : tab === "third" ? service.getThirdPartyConfigs() : tab === "settings" ? service.getSystemSettings() : service.getAppReleases(); task.then((data) => setRows(Array.isArray(data) ? data : Object.entries(data).map(([key, value]) => ({ key, value })))).catch((e) => notice(e instanceof Error ? e.message : "读取系统管理失败")); }, [tab]); const tabs = [{ id: "users", label: "用户管理" }, { id: "models", label: "模型配置" }, { id: "third", label: "第三方 API" }, { id: "settings", label: "业务配置" }, { id: "releases", label: "版本更新" }]; return <section className="admin-page"><div className="admin-tabs">{tabs.map((x) => <button className={tab === x.id ? "active" : ""} key={x.id} onClick={() => setTab(x.id)}>{x.label}</button>)}</div><div className="admin-table"><table><thead><tr><th>名称</th><th>类型</th><th>状态</th><th>信息</th></tr></thead><tbody>{rows.map((row, i) => { const x = row as Record<string, unknown>; return <tr key={i}><td>{String(x.real_name || x.username || x.config_name || x.key || x.version || "-")}</td><td>{String(x.role || x.model_type || x.service_type || "-")}</td><td>{x.status === 1 || x.status === true ? "启用" : "-"}</td><td>{String(x.model_name || x.provider || x.filename || x.value || x.release_notes || "-")}</td></tr>; })}</tbody></table>{!rows.length && <div className="empty-state">暂无数据</div>}</div></section>; }

function Studio({ search }: { search: (message: string, count: number) => Promise<void> }) { const [message, setMessage] = useState(""); const [count, setCount] = useState(10); const [busy, setBusy] = useState(false); return <section className="studio"><div className="studio-intro"><div><em>✦</em><h2>告诉我您想找什么样的产品？</h2><p>例如：最近在日本 TikTok 上热卖的厨房小工具，价格在1000日元以内</p></div><span>AI 选品助手</span></div><div className="prompt-box"><textarea placeholder="告诉我您想找什么样的产品？" value={message} onChange={(e) => setMessage(e.target.value)} /><div className="prompt-bottom"><small>{message.length}/300</small><select value={count} onChange={(e) => setCount(Number(e.target.value))}><option value={10}>10 条 · 10 积分</option><option value={15}>15 条 · 15 积分</option><option value={20}>20 条 · 20 积分</option></select><button className="primary" disabled={!message.trim() || busy} onClick={async () => { setBusy(true); try { await search(message, count); } finally { setBusy(false); } }}>{busy ? "分析中..." : "智能选品"}</button></div></div></section>; }

function Dashboard() { const barRef=useRef<HTMLDivElement>(null); const radarRef=useRef<HTMLDivElement>(null); const [data,setData]=useState<Record<string,unknown>>({}); useEffect(()=>{service.getPipelineStatus().then(x=>setData(x||{})).catch(()=>setData({}));},[]); useEffect(()=>{type Chart={setOption:(option:unknown)=>void;resize:()=>void;dispose:()=>void};type Engine={init:(el:HTMLElement)=>Chart};const run=()=>{const engine=(window as Window & {echarts?:Engine}).echarts;if(!engine||!barRef.current||!radarRef.current)return;const bar=engine.init(barRef.current);const radar=engine.init(radarRef.current);bar.setOption({tooltip:{trigger:"axis"},grid:{left:42,right:18,top:25,bottom:28},xAxis:{type:"category",data:["FastMoss","AI衍生","1688匹配","视频任务"]},yAxis:{type:"value"},series:[{type:"bar",barWidth:28,data:[Number(data.fastmoss_count||12),Number(data.derived_count||8),Number(data.match_count||6),Number(data.video_count||3),],itemStyle:{color:"#168c70",borderRadius:[6,6,0,0]}}]});radar.setOption({tooltip:{},radar:{indicator:[{name:"市场需求",max:100},{name:"短视频适配",max:100},{name:"利润空间",max:100},{name:"新奇特",max:100},{name:"复购属性",max:100},{name:"日本偏好",max:100}],radius:"65%"},series:[{type:"radar",data:[{value:[86,91,78,88,64,84],name:"综合选品画像",areaStyle:{color:"rgba(22,140,112,.22)"},lineStyle:{color:"#168c70"},itemStyle:{color:"#168c70"}}]}]});const resize=()=>{bar.resize();radar.resize()};window.addEventListener("resize",resize);return()=>{window.removeEventListener("resize",resize);bar.dispose();radar.dispose();};};const existing=document.querySelector('script[data-echarts="1"]') as HTMLScriptElement|null;if((window as Window & {echarts?:Engine}).echarts) return run();if(existing){existing.addEventListener("load",run);return()=>existing.removeEventListener("load",run);}const script=document.createElement("script");script.dataset.echarts="1";script.src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js";script.onload=run;document.head.appendChild(script);return()=>{script.onload=null;};},[data]);return <section className="dashboard-page"><div className="dashboard-metrics"><div><span>任务状态</span><b>{String(data.status||"运行中")}</b></div><div><span>今日任务</span><b>{String(data.today_tasks||data.task_count||0)}</b></div><div><span>衍生品数量</span><b>{String(data.derived_count||0)}</b></div><div><span>接口状态</span><b className="ok">在线</b></div></div><div className="dashboard-charts"><section className="chart-card"><h3>业务环节分布</h3><div ref={barRef} className="echart-box"/></section><section className="chart-card"><h3>选品雷达</h3><div ref={radarRef} className="echart-box"/></section></div></section>; }

function StorePage({ user, notice, onCreditChange }: { user: User; notice: (s: string) => void; onCreditChange: (credits: number) => void }) {
  const [links, setLinks] = useState("");
  const [site, setSite] = useState("JP");
  const [language, setLanguage] = useState("ja");
  const [profitRule, setProfitRule] = useState("20");
  const [shops, setShops] = useState<Array<Record<string, unknown>>>([]);
  const [shopId, setShopId] = useState("");
  const [appKey, setAppKey] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [apiBase, setApiBase] = useState("https://openapi-erp.91miaoshou.com");
  const [dryRun, setDryRun] = useState(true);
  const [imageTranslation, setImageTranslation] = useState(true);
  const [imageRemoval, setImageRemoval] = useState(true);
  const [titleOptimization, setTitleOptimization] = useState(true);
  const [skuOptimization, setSkuOptimization] = useState(true);
  const [descriptionOptimization, setDescriptionOptimization] = useState(true);
  const [removeLogo, setRemoveLogo] = useState(true);
  const [removeTransparentText, setRemoveTransparentText] = useState(true);
  const [removeText, setRemoveText] = useState(false);
  const [removePsoriasis, setRemovePsoriasis] = useState(true);
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [shopBusy, setShopBusy] = useState(false);
  const [task, setTask] = useState<Record<string, unknown> | null>(null);

  const offerUrls = useMemo(() => {
    const matches = links.match(/https?:\/\/detail\.1688\.com\/offer\/\d+\.html(?:\?[^\s|，,；;]*)?/gi) || [];
    const ids = links.split(/\r?\n/).map((line) => line.trim()).filter((line) => /^\d{8,}$/.test(line)).map((id) => `https://detail.1688.com/offer/${id}.html`);
    return Array.from(new Set([...matches, ...ids]));
  }, [links]);
  const creditCost = offerUrls.length;
  const balance = Number(user.credits || 0);

  const refresh = async () => {
    try {
      const [a, b] = await Promise.all([service.getPublishLatest(), service.getPublishHistory()]);
      setLatest(a || null);
      setHistory(Array.isArray(b) ? b : []);
      if (a?.task_id && ["created", "running"].includes(String(a.status || ""))) setTask(a);
    } catch (e) { notice(e instanceof Error ? e.message : "读取店铺任务失败"); }
  };
  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (!task?.task_id) return;
    const timer = window.setInterval(async () => {
      try {
        const current = await service.getPublishTask(String(task.task_id));
        setTask(current);
        setLatest(current);
        const status = String(current.status || "");
        if (["imported", "import_failed", "image_failed", "failed", "batch_failed", "batch_partial_failed"].includes(status)) {
          window.clearInterval(timer);
          setBusy(false);
          await refresh();
        }
      } catch (e) { window.clearInterval(timer); setBusy(false); notice(e instanceof Error ? e.message : "读取上架进度失败"); }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [task?.task_id]);

  async function loadShops() {
    setShopBusy(true);
    try {
      const result = await service.getMiaoshouShops({ target_site: site, miaoshou_app_key: appKey, miaoshou_app_secret: appSecret, miaoshou_api_base_url: apiBase });
      const options = Array.isArray(result?.shop_options) ? result.shop_options : [];
      setShops(options);
      if (options[0]?.shop_id) setShopId(String(options[0].shop_id));
      notice(`已读取 ${options.length} 个妙手店铺`);
    } catch (e) { notice(e instanceof Error ? e.message : "读取妙手店铺失败"); }
    finally { setShopBusy(false); }
  }

  async function submit() {
    if (!offerUrls.length) { notice("请先填写 1688 商品链接，每行一个"); return; }
    if (!shopId) { notice("请先刷新并选择妙手店铺"); return; }
    if (creditCost > balance) { notice(`积分不足，本次需要 ${creditCost} 积分`); return; }
    setBusy(true);
    try {
      const result = await service.createPublishBatch({
        offer_urls: offerUrls,
        items: offerUrls.map((offer_url) => ({ offer_url, package_weight_g: 500, package_length_cm: 10, package_width_cm: 10, package_height_cm: 40, profit_rule: profitRule, pricing_currency: "CNY" })),
        publish_count: offerUrls.length, target_channel: "TikTok Shop Japan", target_language: language, target_site: site, target_shop_id: Number(shopId),
        miaoshou_app_key: appKey, miaoshou_app_secret: appSecret, miaoshou_api_base_url: apiBase,
        enable_image_translation: imageTranslation, enable_image_removal: imageRemoval, enable_title_optimization: titleOptimization, enable_sku_optimization: skuOptimization, enable_description_optimization: descriptionOptimization,
        remove_logo: removeLogo, remove_transparent_text: removeTransparentText, remove_text: removeText, remove_psoriasis: removePsoriasis, profit_rule: profitRule, pricing_currency: "CNY", dry_run: dryRun,
      });
      if (typeof result.credit_balance === "number") onCreditChange(result.credit_balance);
      setTask(result); setLatest(result);
      await service.runPublishTask(String(result.task_id));
      notice(`已提交 ${offerUrls.length} 条上架任务`);
    } catch (e) { setBusy(false); notice(e instanceof Error ? e.message : "上架任务提交失败"); }
  }

  const progress = (task?.progress || {}) as Record<string, unknown>;
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  const check = (label: string, value: boolean, setValue: (next: boolean) => void) => <label className="store-check"><input type="checkbox" checked={value} onChange={(e) => setValue(e.target.checked)} />{label}</label>;
  return <section className="store-page">
    <div className="store-heading"><div><h2>店铺管理</h2><p>配置店铺后，填写链接并开始执行。每上架一条商品消耗 1 积分。</p></div><div className="store-balance">当前积分 <b>{balance}</b></div></div>
    <div className="store-layout">
      <div className="store-main">
        <section className="store-card"><div className="store-card-heading"><div><h3>妙手店铺配置</h3><p>使用妙手开放平台 API 读取店铺并执行上架。</p></div><button onClick={loadShops} disabled={shopBusy}>{shopBusy ? "读取中..." : "刷新店铺"}</button></div><div className="store-form-grid"><label>目标地区<select value={site} onChange={(e) => { setSite(e.target.value); setShops([]); setShopId(""); }}><option value="JP">日本</option><option value="US">美国</option><option value="GB">英国</option></select></label><label>目标语言<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="ja">日语</option><option value="en">英语</option></select></label><label className="store-span-2">目标店铺<select value={shopId} onChange={(e) => setShopId(e.target.value)}><option value="">请先刷新店铺</option>{shops.map((shop) => <option value={String(shop.shop_id)} key={String(shop.shop_id)}>{String(shop.shop_name || `店铺 ${shop.shop_id}`)} · {String(shop.shop_id)}</option>)}</select></label><label>AppKey<input value={appKey} onChange={(e) => setAppKey(e.target.value)} placeholder="妙手 AppKey" /></label><label>AppSecret<input type="password" value={appSecret} onChange={(e) => setAppSecret(e.target.value)} placeholder="妙手 AppSecret" /></label><label className="store-span-2">API Base URL<input value={apiBase} onChange={(e) => setApiBase(e.target.value)} /></label></div></section>
        <section className="store-card"><div className="store-card-heading"><div><h3>1688 商品链接</h3><p>每行一个链接，也支持直接填写 1688 商品 ID。</p></div><span className="store-count">已识别 {offerUrls.length} 条</span></div><textarea className="store-links" value={links} onChange={(e) => setLinks(e.target.value)} placeholder="https://detail.1688.com/offer/1234567890.html" /></section>
        <section className="store-card"><h3>上架处理选项</h3><div className="store-option-group"><b>商品内容</b><div className="store-checks">{check("妙手文案 / 标题优化", titleOptimization, setTitleOptimization)}{check("规格优化", skuOptimization, setSkuOptimization)}{check("产品描述优化", descriptionOptimization, setDescriptionOptimization)}{check("图片翻译", imageTranslation, setImageTranslation)}{check("图片智能抹除", imageRemoval, setImageRemoval)}</div></div><div className="store-option-group"><b>图片处理</b><div className="store-checks">{check("去除 LOGO", removeLogo, setRemoveLogo)}{check("去除透明字块", removeTransparentText, setRemoveTransparentText)}{check("去除文字", removeText, setRemoveText)}{check("去除牛皮癣", removePsoriasis, setRemovePsoriasis)}</div></div><div className="store-form-grid store-bottom-form"><label>目标利润<input value={profitRule} onChange={(e) => setProfitRule(e.target.value)} placeholder="例如 20 或 20%" /></label><label className="store-switch"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />仅保存不发布</label></div></section>
        <section className="store-card store-submit"><div><b>准备处理 {offerUrls.length} 条商品</b><span>预计消耗 {creditCost} 积分 · 余额 {balance}</span></div><button className="primary" disabled={busy || !offerUrls.length || !shopId || creditCost > balance} onClick={submit}>{busy ? "任务处理中..." : "开始上架"}</button></section>
      </div>
      <aside className="store-side"><section className="store-card store-progress"><div className="store-card-heading"><h3>任务进度</h3><button onClick={refresh}>刷新</button></div>{task ? <><div className="store-progress-line"><b>{percent}%</b><span>{String(progress.message || task.message || task.status || "等待执行")}</span></div><i><em style={{ width: `${percent}%` }} /></i><p>任务 ID：{String(task.task_id || "-")}</p></> : <div className="store-empty">暂无进行中的任务</div>}</section><section className="store-card"><h3>最近任务</h3><div className="store-history">{history.slice(0, 8).map((item, index) => <div key={String(item.task_id || index)}><b>{String(item.workflow || "自动上架任务")}</b><span>{String(item.status || "-")} · {String(item.created_at || "")}</span><small>{Array.isArray(item.offer_urls) ? `${item.offer_urls.length} 条链接` : String(item.offer_url || "")}</small></div>)}{!history.length && <div className="store-empty">暂无历史任务</div>}</div></section></aside>
    </div>
  </section>;
}

function VideoPage({ user, notice, onCreditChange }: { user: User; notice: (s: string) => void; onCreditChange: (credits: number) => void }) { const [projects,setProjects]=useState<VideoProject[]>([]); const [project,setProject]=useState<VideoProject|null>(null); const [step,setStep]=useState(0); const [titleValue,setTitleValue]=useState(""); const [market,setMarket]=useState("日本"); const [language,setLanguage]=useState("日语"); const [details,setDetails]=useState(""); const [strategy,setStrategy]=useState("auto_safe"); const [script,setScript]=useState(""); const [files,setFiles]=useState<File[]>([]); const [role,setRole]=useState("产品主图"); const [desc,setDesc]=useState(""); const [model,setModel]=useState("auto"); const [models,setModels]=useState<Array<{label?:string;value?:string}>>([]); const [busy,setBusy]=useState(false); const [taskBusy,setTaskBusy]=useState(false); const selectProject=(p:VideoProject)=>{setProject(p);setTitleValue(p.title||"");setMarket(p.target_market||"日本");setLanguage(p.video_language||"日语");setDetails(p.product_details||"");setScript(p.script_text||"");}; const refresh=async()=>{try{const rows=await service.getVideoProjects();setProjects(rows);if(!project&&rows[0])selectProject(rows[0]);}catch(e){notice(e instanceof Error?e.message:"读取视频项目失败");}}; useEffect(()=>{refresh();service.getVideoModels().then(setModels).catch(()=>setModels([]));},[]); async function createProject(){setBusy(true);try{const p=await service.createVideoProject({title:titleValue||"新视频项目",target_market:market,video_language:language,product_details:details+"\nvideo_strategy_key:"+strategy});setProjects(r=>[p,...r]);selectProject(p);notice("视频项目已创建");}catch(e){notice(e instanceof Error?e.message:"创建项目失败");}finally{setBusy(false);}} async function saveInfo(){if(!project){await createProject();return;}setBusy(true);try{const p=await service.updateVideoProject(project.id,{title:titleValue||"新视频项目",target_market:market,video_language:language,product_details:details+"\nvideo_strategy_key:"+strategy});setProject(p);setProjects(r=>r.map(x=>x.id===p.id?p:x));notice("产品信息已保存");}catch(e){notice(e instanceof Error?e.message:"保存产品信息失败");}finally{setBusy(false);}} async function upload(){if(!project){notice("请先保存项目");return;}if(!files.length){notice("请选择产品图片");return;}setBusy(true);try{let p=project;for(let i=0;i<files.length;i++)p=await service.uploadVideoAsset(project.id,files[i],{role,description:desc,is_primary:i===0?1:0});setProject(p);setProjects(r=>r.map(x=>x.id===p.id?p:x));setFiles([]);notice("产品图上传完成");}catch(e){notice(e instanceof Error?e.message:"上传图片失败");}finally{setBusy(false);}} async function generate(){if(!project){notice("请先保存项目");return;}setBusy(true);try{const p=await service.generateVideoScript(project.id);setProject(p);setScript(p.script_text||"");setStep(2);notice("AI脚本已生成");}catch(e){notice(e instanceof Error?e.message:"脚本生成失败");}finally{setBusy(false);}} async function saveScript(){if(!project)return;setBusy(true);try{const p=await service.saveVideoScript(project.id,{script_text:script,storyboard:[]});setProject(p);setProjects(r=>r.map(x=>x.id===p.id?p:x));notice("脚本已保存");}catch(e){notice(e instanceof Error?e.message:"保存脚本失败");}finally{setBusy(false);}} async function submit(){if(!project){notice("请先保存项目");return;}if(Number(user.credits||0)<100){notice("积分不足，提交生成视频需要100积分");return;}if(!project.assets?.length){notice("请先上传产品图");return;}await saveScript();setTaskBusy(true);try{const p=await service.submitVideoTask(project.id,{generation_mode:"image_to_video",model_name:model});if(typeof p.credit_balance==="number")onCreditChange(p.credit_balance);setProject(p);setProjects(r=>r.map(x=>x.id===p.id?p:x));setStep(3);notice("视频任务已提交");}catch(e){notice(e instanceof Error?e.message:"提交视频失败");}finally{setTaskBusy(false);}} const task=project?.tasks?.[0]; const video=task?.video_url||task?.result_video_url||project?.result_video_url; const url=(v?:string)=>v?(v.startsWith("http")?v:String(service.api.defaults.baseURL||"")+v):""; const opts=models.length?models:[{label:"默认推荐",value:"auto"},{label:"Seedance 2.0 Fast",value:"doubao-seedance-2-0-fast"},{label:"即梦电商特价",value:"buming:seedance-2-0-ecom-special"}]; return <section className="video-page"><div className="video-heading"><div><h2>视频生成</h2><p>上传产品图，生成脚本，再提交视频。产品图会作为强参考。提交生成视频消耗 100 积分。</p></div><div className="video-credit">当前积分 <b>{user.credits??0}</b></div></div><div className="video-layout"><aside className="video-projects"><div className="video-projects-head"><h3>我的项目</h3><button onClick={refresh}>刷新</button></div>{projects.map(p=><button key={p.id} className={project?.id===p.id?"video-project active":"video-project"} onClick={()=>selectProject(p)}><b>{p.title||("项目 "+p.id)}</b><span>{p.status||"draft"}</span></button>)}{!projects.length&&<div className="video-empty">暂无项目</div>}</aside><div className="video-workspace"><div className="video-steps">{["产品信息","产品图片","视频脚本","生成视频"].map((x,i)=><button key={x} className={step===i?"active":""} onClick={()=>setStep(i)}><i>{i+1}</i>{x}</button>)}</div>{step===0&&<section className="video-card"><h3>第 1 步：填写产品信息</h3><div className="video-form-grid"><label>项目标题<input value={titleValue} onChange={e=>setTitleValue(e.target.value)}/></label><label>目标市场<select value={market} onChange={e=>setMarket(e.target.value)}><option>日本</option><option>美国</option><option>英国</option><option>东南亚</option></select></label><label>字幕/口播语言<select value={language} onChange={e=>setLanguage(e.target.value)}><option>日语</option><option>英语</option><option>中文</option><option>韩语</option></select></label><label>拍摄方案<select value={strategy} onChange={e=>setStrategy(e.target.value)}><option value="auto_safe">自动稳妥</option><option value="static_display">静态展示</option><option value="light_interaction">轻交互</option><option value="handheld_demo">手持演示</option><option value="wearable_demo">佩戴演示</option></select></label><label className="video-span-2">产品详情<textarea value={details} onChange={e=>setDetails(e.target.value)} placeholder="粘贴产品详情、卖点、人群、场景、风格要求。"/></label></div><div className="video-actions"><button className="primary" onClick={createProject} disabled={busy}>保存为新项目</button><button onClick={saveInfo} disabled={busy||!project}>保存当前产品信息</button></div></section>}{step===1&&<section className="video-card"><h3>第 2 步：上传产品图</h3><div className="video-upload-row"><input value={role} onChange={e=>setRole(e.target.value)} placeholder="图片角色"/><input value={desc} onChange={e=>setDesc(e.target.value)} placeholder="图片说明"/><input type="file" accept="image/*" multiple onChange={e=>setFiles(Array.from(e.target.files||[]))}/><button className="primary" onClick={upload} disabled={busy||!files.length||!project}>上传图片</button></div><div className="video-assets">{(project?.assets||[]).map(a=><article key={a.id}><div className="video-asset-image">{url(a.public_url||a.url)?<img src={url(a.public_url||a.url)}/>:<span>暂无图片</span>}</div><div><b>{a.role||"产品图片"}</b><p>{a.description||"无说明"}</p><small>{a.is_primary?"主参考图":"参考图"}</small></div><button onClick={async()=>{if(project){try{const p=await service.deleteVideoAsset(project.id,a.id);setProject(p);notice("图片已删除");}catch(e){notice(e instanceof Error?e.message:"删除失败");}}}}>删除</button></article>)}{!project?.assets?.length&&<div className="video-empty">暂无产品图</div>}</div></section>}{step===2&&<section className="video-card"><h3>第 3 步：生成并修改脚本</h3><div className="video-actions"><button className="primary" onClick={generate} disabled={busy||!project}>AI 生成脚本</button><button onClick={saveScript} disabled={busy||!project}>保存修改后的脚本</button></div><textarea className="video-script" value={script} onChange={e=>setScript(e.target.value)} placeholder="点击 AI 生成脚本，或直接输入脚本。"/></section>}{step===3&&<section className="video-card video-generate-card"><h3>第 4 步：生成视频</h3><div className="video-submit-row"><label>生成方案<select value={model} onChange={e=>setModel(e.target.value)}>{opts.map(o=><option key={o.value} value={o.value}>{o.label||o.value}</option>)}</select></label><button className="primary" onClick={submit} disabled={taskBusy||!project}>提交生成视频 · 100积分</button></div><div className="video-status"><b>当前状态：{task?.status||project?.status||"未提交"}</b><span>{task?.provider_task_id?"任务号："+task.provider_task_id:"尚未提交任务"}</span>{task?.error_message&&<p className="video-error">{task.error_message}</p>}</div>{video?<video className="video-preview" controls src={url(video)}/>:<div className="video-preview-empty">生成完成后会在这里预览视频</div>}<button onClick={async()=>{if(project&&task?.id){try{setProject(await service.refreshVideoTask(project.id,task.id));notice("任务已刷新");}catch(e){notice(e instanceof Error?e.message:"刷新失败");}}}}>刷新任务</button></section>}</div></div></section>; }

function WindowTitlebar() { return <div className="window-titlebar"><div className="window-brand"><span className="window-brand-mark">TK</span><strong>益行跨境 AI 平台</strong></div><div className="window-tools"><button aria-label="Help" title="Help">?</button><button aria-label="Messages" title="Messages">MSG</button><button aria-label="Settings" title="Settings">SET</button><div className="window-controls"><button aria-label="Minimize" title="Minimize" onClick={() => window.desktop?.minimize()}>-</button><button aria-label="Maximize" title="Maximize" onClick={() => window.desktop?.toggleMaximize()}>[]</button><button className="close" aria-label="Close" title="Close" onClick={() => window.desktop?.close()}>X</button></div></div></div>; } /*

export default function App2() { const stored = localStorage.getItem("tk_electron_user"); const [user, setUser] = useState<User | null>(() => stored ? JSON.parse(stored) : null); const [page, setPage] = useState<Page>("studio"); const [rows, setRows] = useState<Product[]>([]); const [selected, setSelected] = useState<Product | null>(null); const [notice, setNotice] = useState(""); const allowed = useMemo(() => menus.filter((m) => m.roles.includes(user?.role || "student")), [user]); const flash = (s: string) => { setNotice(s); window.setTimeout(() => setNotice(""), 3000); }; async function load(next: Page) { if (!["library", "rank", "favorites"].includes(next)) return; try { const data = next === "library" ? await service.getLibrary() : next === "favorites" ? await service.getFavorites() : await service.getRanks({ region: "JP", list_type: "new", page: 1, pagesize: 50, paged: true }); const list = Array.isArray(data) ? data : (data as { items?: Product[] })?.items || []; setRows(list); setSelected(list[0] || null); } catch (e) { flash(e instanceof Error ? e.message : "读取数据失败"); } } useEffect(() => { if (user) load(page); }, [user, page]); if (!user) return <><WindowTitlebar /><Login done={setUser} /></>; const collect = async (p: Product) => { try { await service.collect(p); flash("已加入采集箱"); } catch (e) { flash(e instanceof Error ? e.message : "加入失败"); } }; return <><WindowTitlebar /><div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">TK</div><div><b>益行跨境 AI 平台</b><span>TikTok 日本选品专家</span></div></div><nav>{allowed.map((m) => <button key={m.id} className={page === m.id ? "active" : ""} onClick={() => setPage(m.id)}><i>{m.icon}</i>{m.label}</button>)}</nav><div className="account"><div className="avatar">{(user.real_name || user.username || "系").slice(0, 1)}</div><div className="account-copy"><b>{user.real_name || user.username}</b><span>{user.role} · 积分 {user.credits ?? 0}</span></div><button className="logout" onClick={() => { service.logout(); setUser(null); }}>退出登录</button></div></aside><main className="main"><header><div><h1>{menus.find((m) => m.id === page)?.label}</h1><span>益行跨境 · 日本市场选品工作台</span></div></header>{page === "studio" && <Studio search={async (message, count) => { await service.searchSelection(message, count); flash("选品完成，结果已进入选品库"); setPage("library"); }} />}{["library", "rank", "favorites"].includes(page) && <Products page={page} rows={rows} selected={selected} onSelect={setSelected} onCollect={collect} />}{page === "dashboard" && <Dashboard />}{page === "store" && <Store notice={flash} />}{page === "video" && <Video notice={flash} />}{page === "profile" && <div className="module-card"><h2>个人中心</h2><p>当前账号：{user.username || user.real_name}</p><p>当前积分：{user.credits ?? 0}</p></div>}{page === "teacher" && <Teacher notice={flash} />}{page === "admin" && <Admin notice={flash} />}{notice && <div className="toast">{notice}</div>}</main></div>; }
*/

function Profile({ user, onNotice, onCreditChange }: { user: User; onNotice: (message: string) => void; onCreditChange: (credits: number) => void }) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showQr, setShowQr] = useState(false);
  const [opacity, setOpacity] = useState(() => JSON.parse(localStorage.getItem("tk_theme") || "{}").opacity || "0.30");
  const credits = Number(user.credits ?? user.credit_balance ?? 0);
  function updateOpacity(value: string) {
    setOpacity(value);
    const saved = JSON.parse(localStorage.getItem("tk_theme") || "{}");
    const next = { font: "Microsoft YaHei UI", size: "14px", background: "background.png", ...saved, opacity: value };
    localStorage.setItem("tk_theme", JSON.stringify(next));
    applyTheme(next);
  }
  return <section className="profile">
    <div className="profile-card"><div className="avatar large-avatar">{(user.real_name || user.username || "A").slice(0, 1)}</div><div><h2>{user.real_name || user.username}</h2><p>{user.role} · 当前积分 <b className="profile-credit">{credits}</b></p></div><button className="secondary profile-refresh" onClick={async () => { try { const fresh = await service.getUser(); onCreditChange(Number(fresh.credits ?? fresh.credit_balance ?? 0)); onNotice("积分余额已刷新"); } catch (e) { onNotice(e instanceof Error ? e.message : "刷新积分失败"); } }}>刷新余额</button></div>
    <div className="settings-card credit-card"><h2>积分中心</h2><div className="credit-balance"><strong>{credits}</strong><span>当前可用积分</span></div><p>积分用于智能选品、衍生品生成、视频生成和自动上架等功能。</p><button className="primary" onClick={() => setShowQr(true)}>扫码联系管理员充值</button></div>
    <div className="settings-card"><h2>修改密码</h2><label>原密码<input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} /></label><label>新密码<input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label><button className="primary" onClick={async () => { try { await service.changePassword(oldPassword, newPassword); onNotice("密码已更新"); setOldPassword(""); setNewPassword(""); } catch (e) { onNotice(e instanceof Error ? e.message : "修改失败"); } }}>保存新密码</button></div>
    <div className="settings-card transparency-settings"><h2>软件透明度</h2><p>调整菜单栏和内容区的透明显现程度，修改会即时生效。</p><label className="opacity-control"><span>透明度 {Math.round(Number(opacity) * 100)}%</span><input type="range" min="0.12" max="0.72" step="0.02" value={opacity} onChange={(e) => updateOpacity(e.target.value)} /></label></div>
    {showQr && <div className="modal-backdrop" onClick={() => setShowQr(false)}><div className="modal recharge-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={() => setShowQr(false)}>×</button><h2>积分充值</h2><p>扫码添加管理员好友，发送登录账号、充值金额和希望获得的积分。</p><img src="/recharge_qr.png" alt="积分充值二维码" /><small>充值到账后，点击“刷新余额”即可查看。</small></div></div>}
  </section>;
}

function reportText(item: Product) {
  if (typeof item.analysis_report === "string") return item.analysis_report;
  return JSON.stringify(item.analysis_report || "");
}

function reportHas(item: Product, keyword: string) {
  return reportText(item).includes(keyword);
}

function downloadReport(item: Product) {
  const payload = {
    title: title(item),
    price: money(item),
    sales: item.sales_count ?? item.supplier_sales_count ?? 0,
    image_url: picture(item),
    region: item.region,
    category: item.category,
    analysis_report: item.analysis_report || "暂无分析报告",
    exported_at: new Date().toLocaleString("zh-CN"),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${title(item).slice(0, 30) || "选品分析报告"}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function LibraryPage({ rows, onNotice }: { rows: Product[]; onNotice: (message: string) => void }) {
  const [region, setRegion] = useState("ALL");
  const [category, setCategory] = useState("全部");
  const [selected, setSelected] = useState<Product | null>(null);
  const [regions, setRegions] = useState<Array<{ region_name?: string; region_code?: string }>>([]);
  const [reportTab, setReportTab] = useState<"first" | "last">("first");
  const [favorites, setFavorites] = useState<Product[]>([]);
  const dimensions = ["使用场景", "商品周期性", "目标群体", "短视频流量种草适配能力", "日本市场偏好", "是否属于新奇特商品", "复购属性", "竞品属性"];
  const categories = ["全部", "美妆个护", "女装与女士内衣", "保健", "时尚配件", "运动与户外", "手机与数码", "居家日用", "食品饮料", "玩具和爱好"];

  useEffect(() => { setSelected(rows[0] || null); service.getRegions().then((items) => setRegions(items.length ? items : DEFAULT_REGIONS)).catch(() => setRegions(DEFAULT_REGIONS)); service.getFavorites().then((items) => setFavorites(Array.isArray(items) ? items : [])).catch(() => setFavorites([])); }, [rows]);
  const filtered = useMemo(() => rows.filter((item) => {
    const itemRegion = String(item.region || "").toUpperCase();
    const itemCategory = String(item.category || "");
    const regionMatch = region === "ALL" || itemRegion === region || (region === "SEA" && ["ID", "VN", "TH", "MY", "PH", "SG"].includes(itemRegion));
    const aliases: Record<string, string[]> = { "美妆个护": ["美妆个护", "Beauty & Personal Care"], "女装与女士内衣": ["女装与女士内衣", "Womenswear & Underwear"], "保健": ["保健", "Health"], "时尚配件": ["时尚配件", "Fashion Accessories"], "运动与户外": ["运动与户外", "Sports & Outdoor"], "手机与数码": ["手机与数码", "Phones & Electronics"], "居家日用": ["居家日用", "Home Supplies"], "食品饮料": ["食品饮料", "Food & Beverage"], "玩具和爱好": ["玩具和爱好", "Toys & Hobbies"] };
    const categoryMatch = category === "全部" || (aliases[category] || [category]).some((value) => itemCategory.toLowerCase().includes(value.toLowerCase()));
    return regionMatch && categoryMatch;
  }), [rows, region, category]);
  useEffect(() => { if (selected && !filtered.some((item) => pid(item) === pid(selected))) setSelected(filtered[0] || null); }, [filtered]);
  const visibleDimensions = reportTab === "first" ? dimensions.slice(0, 6) : dimensions.slice(6);
  const saved = selected && favorites.some((item) => title(item) === title(selected) && picture(item) === picture(selected));
  async function collect() { if (!selected) return; try { const response = await service.collect(selected); setFavorites((list) => [response?.data || selected, ...list]); onNotice("已加入采集箱"); } catch (e) { onNotice(e instanceof Error ? e.message : "加入采集箱失败"); } }
  return <section className="library-page">
    <div className="library-heading"><div><h2>选品库</h2><p>查看当前账号最近 7 天的 AI 搜索选品结果</p></div></div>
    <div className="library-filters"><div className="library-filter-row"><b>国家/地区：</b><button className={region === "ALL" ? "active" : ""} onClick={() => setRegion("ALL")}>全部</button>{regions.map((item) => <button key={item.region_code} className={region === item.region_code ? "active" : ""} onClick={() => setRegion(String(item.region_code || ""))}>{item.region_name || item.region_code}</button>)}</div><div className="library-filter-row"><b>商品分类：</b>{categories.map((item) => <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item}</button>)}</div></div>
    <div className="library-workspace"><section><div className="smart-section-title"><h2>我的搜索选品</h2><span>{filtered.length} 个商品</span></div><div className="library-grid">{filtered.map((item) => <article key={String(pid(item))} className={selected && pid(selected) === pid(item) ? "library-card selected" : "library-card"} onClick={() => setSelected(item)}><div className="library-card-image">{picture(item) ? <img src={picture(item)} loading="lazy" /> : <div className="image-empty">暂无图片</div>}</div><h3>{title(item)}</h3><div className="library-card-meta"><strong>{money(item)}</strong><span>销量 {Number(item.sales_count ?? item.supplier_sales_count ?? 0).toLocaleString()}</span></div><button onClick={(e) => { e.stopPropagation(); collect(); }}>{saved && selected && pid(selected) === pid(item) ? "已在采集箱" : "加入采集箱"}</button></article>)}</div>{!filtered.length && <div className="empty-state">暂无搜索选品，请先在智能选品对话框提交需求。</div>}</section><aside className="library-report"><h2>选品分析报告</h2>{selected ? <><div className="smart-report-product">{picture(selected) ? <img src={picture(selected)} /> : <div className="image-empty">暂无图片</div>}<div><h3>{title(selected)}</h3><strong>{money(selected)}</strong><p>销量 {Number(selected.sales_count ?? selected.supplier_sales_count ?? 0).toLocaleString()}</p><p>AI 参考分 {Number(selected.ai_score ?? selected.weighted_score ?? 0).toFixed(1)}</p></div></div><div className="smart-report-tabs"><button className={reportTab === "first" ? "active" : ""} onClick={() => setReportTab("first")}>选品分析 1-6</button><button className={reportTab === "last" ? "active" : ""} onClick={() => setReportTab("last")}>选品分析 7-8</button></div><div className="smart-dimensions">{visibleDimensions.map((name, index) => <div key={name}><span className="smart-dimension-icon">{index + 1}</span><div><b>{name}</b><small>{reportHas(selected, name) ? "已生成分析报告" : "暂无分析内容"}</small></div><strong>{reportHas(selected, name) ? "参考" : "-"}</strong></div>)}</div><div className="smart-report-actions"><button className="secondary" onClick={collect}>{saved ? "★ 已在采集箱" : "☆ 加入采集箱"}</button><button className="primary" onClick={() => downloadReport(selected)}>⇩ 导出报告</button></div></> : <div className="empty-state">选择商品查看分析</div>}</aside></div>
  </section>;
}

function SmartSelection({ user, onNotice, onOpenLibrary, onCreditChange }: { user: User; onNotice: (message: string) => void; onOpenLibrary: () => void; onCreditChange: (credits: number) => void }) {
  const [message, setMessage] = useState("");
  const [count, setCount] = useState(10);
  const [items, setItems] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const hotSearches = ["日本家居收纳好物", "夏季防晒类商品", "学生党平价好物", "母婴用品选品", "厨房小工具"];
  const [taskId, setTaskId] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [taskMessage, setTaskMessage] = useState("");
  const [reportTab, setReportTab] = useState<"first" | "last">("first");
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [busy, setBusy] = useState(false);
  const [flowStatus, setFlowStatus] = useState<"idle" | "running" | "success" | "failed">("idle");
  const [flowStep, setFlowStep] = useState(-1);
  const requiredCredits = count;
  const dimensions = ["使用场景", "商品周期性", "目标群体", "短视频流量种草适配能力", "日本市场偏好", "是否属于新奇特商品", "复购属性", "竞品属性"];
  const flowNodes = [
    { title: "步骤 1：AI 对话挖掘潜力爆品", description: "输入需求对话，AI 精准拆解日本本土消费需求，自动产出 10 款适配 TK 日区短视频流量的潜力新品，清晰罗列完整商品名称。" },
    { title: "步骤 2：全网数据拓品，摸清市场全貌", description: "抓取 TikTok 日本站前台真实在售数据，围绕核心款拓展出 100 款同赛道关联商品，完整掌握类目款式、热度、定价大盘。" },
    { title: "步骤 3：多维风控过滤，规避全部运营雷区", description: "依托益行深耕对日跨境的实战经验库，一次性筛除禁运禁售、专利侵权、平台限售、海关报关受限等高风险商品，从源头杜绝封号、扣货损失。" },
    { title: "步骤 4：热销竞品规避，抢占蓝海赛道", description: "自动比对平台现有爆款数据，直接剔除内卷严重的成熟热销品，帮你避开红海厮杀，优先锁定竞争小、增量空间足的蓝海单品。" },
    { title: "步骤 5：自动生成专业可视化选品报告", description: "一键输出完整决策报告，包含类目市场调研、精准产品定位画像、目标受众分析、全维度风险预警、平台限售标注，选品有据可依。" },
    { title: "步骤 6：智能匹配 1688 优质供应链", description: "定向筛选江浙沪极速发货货源，自动核算毛利空间，优先剔除差评多、售后差、起订门槛高的供应商，锁定高利润稳定货源。" },
    { title: "步骤 7：输出最终精选 10 款优质爆品", description: "经过流量、合规、竞争、利润、供应链多层筛选，交付综合评分最优的 10 款可直接上架运营的商品清单。" },
  ];

  const refresh = async () => {
    try {
      const recommendations = await service.getRecommendations(12);
      const list = Array.isArray(recommendations) ? recommendations : [];
      setItems(list.map((item) => ({ ...item, region: "CN", currency: "CNY" })));
      setSelected((current) => current && list.some((item) => pid(item) === pid(current)) ? current : list[0] || null);
    } catch (e) { onNotice(e instanceof Error ? e.message : "读取今日推荐失败"); }
    try {
      const saved = await service.getFavorites();
      setFavorites(Array.isArray(saved) ? saved : []);
    } catch {
      setFavorites([]);
    }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (!taskId) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await service.getSelectionTask(taskId);
        setProgress(Math.max(0, Math.min(100, Number(status.progress || 0))));
        setTaskMessage(String(status.message || status.stage || "正在生成选品"));
        setFlowStep(Math.min(flowNodes.length - 1, Math.max(0, Math.floor(Number(status.progress || 0) / 10))));
        if (status.status === "success") {
          window.clearInterval(timer); setTaskId(null); setBusy(false); setProgress(100); setFlowStep(flowNodes.length - 1); setFlowStatus("success");
          onNotice(`选品完成，共生成 ${status.success_count || count} 个商品`);
          window.setTimeout(onOpenLibrary, 700);
        } else if (status.status === "failed") {
          window.clearInterval(timer); setTaskId(null); setBusy(false); setFlowStatus("failed"); onNotice(String(status.message || "选品失败，积分已按后端结果处理"));
        }
      } catch (e) { window.clearInterval(timer); setTaskId(null); setBusy(false); onNotice(e instanceof Error ? e.message : "任务查询失败"); }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [taskId, count]);

  async function submit() {
    if (!message.trim() || busy) return;
    if (Number(user.credits ?? 0) < requiredCredits) { onNotice(`积分不足，本次需要 ${requiredCredits} 积分，请前往个人中心充值`); return; }
    setBusy(true); setProgress(5); setTaskMessage("正在提交 AI 选品任务");
    try {
      const result = await service.searchSelection(message.trim(), count);
      if (!result.task_id) throw new Error("后端没有返回选品任务编号");
      if (typeof result.credit_balance === "number") { user.credits = result.credit_balance; onCreditChange(result.credit_balance); }
      setTaskId(Number(result.task_id));
    } catch (e) { setBusy(false); setProgress(0); setFlowStep(-1); setFlowStatus("failed"); onNotice(e instanceof Error ? e.message : "启动选品失败"); }
  }

  function isFavorite(item: Product) { return favorites.some((saved) => title(saved) === title(item) && picture(saved) === picture(item)); }
  async function collect() {
    if (!selected) return;
    try { const saved = await service.collect(selected); setFavorites((list) => [saved?.data || selected, ...list]); onNotice("已加入采集箱"); } catch (e) { onNotice(e instanceof Error ? e.message : "加入采集箱失败"); }
  }
  const visibleDimensions = reportTab === "first" ? dimensions.slice(0, 6) : dimensions.slice(6);
  const flowClass = (index: number) => index < flowStep ? "flow-node done" : index === flowStep ? `flow-node active ${flowStatus}` : "flow-node";
  return <section className="smart-selection">
    <div className="smart-heading"><div><h2>AI 智能选品</h2><p>AI 全自动 TK 日区选品，五层严筛出 10 款可上架爆品，省时避坑、利润可控！</p></div><button className="tutorial-button" onClick={() => onNotice("描述商品、人群、预算或使用场景，点击智能选品提交任务。")}>◉ 使用教程</button></div>
    <div className="smart-workspace">
      <div className="smart-main">
        <div className="smart-chat"><div className="smart-chat-title"><span>✦</span><b>告诉我您想找什么样的产品？</b><small>AI 选品助手</small></div><textarea value={message} maxLength={300} placeholder="输入类目，挖掘 TK 日站蓝海爆品" onChange={(e) => setMessage(e.target.value)} disabled={busy} /><div className="smart-controls"><span>{message.length}/300</span><select value={count} onChange={(e) => setCount(Number(e.target.value))} disabled={busy}><option value={10}>10 条 · 10 积分</option><option value={15}>15 条 · 15 积分</option><option value={20}>20 条 · 20 积分</option></select><button className="primary" disabled={!message.trim() || busy} onClick={submit}>智能选品</button></div><div className="smart-hot-searches"><b>热门搜索：</b>{hotSearches.map((item) => <button key={item} type="button" onClick={() => setMessage(item)} disabled={busy}>{item}</button>)}</div>{busy && <div className="smart-progress"><div><span>{taskMessage || "正在选品"}</span><b>{progress}%</b></div><i><em style={{ width: `${progress}%` }} /></i></div>}</div>
        <div className="selection-flow-panel"><div className="selection-flow-heading"><div><h2>智能选品流程</h2><p>{flowStatus === "idle" ? "点击智能选品后，实时查看每一步执行进度" : flowStatus === "success" ? "选品流程已完成，正在打开选品库" : flowStatus === "failed" ? "流程执行失败，请根据提示检查任务" : `正在执行第 ${Math.min(flowNodes.length, flowStep + 1)} 步`}</p></div><span className={`flow-status ${flowStatus}`}>{flowStatus === "success" ? "已完成" : flowStatus === "failed" ? "执行失败" : flowStatus === "running" ? "执行中" : "待开始"}</span></div><div className="selection-flow-row">{flowNodes.slice(0, 2).map((node, index) => <React.Fragment key={node.title}><div className={flowClass(index)}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{node.title}</b><small>{node.description}</small></div><i>{index < flowStep ? "✓" : index === flowStep && flowStatus === "running" ? "●" : ""}</i></div>{index < 1 && <em className={index < flowStep ? "flow-link done" : "flow-link"}>→</em>}</React.Fragment>)}</div><div className="selection-flow-row">{flowNodes.slice(2, 4).map((node, index) => { const actual = index + 2; return <React.Fragment key={node.title}><div className={flowClass(actual)}><span>{String(actual + 1).padStart(2, "0")}</span><div><b>{node.title}</b><small>{node.description}</small></div><i>{actual < flowStep ? "✓" : actual === flowStep && flowStatus === "running" ? "●" : ""}</i></div>{index < 1 && <em className={actual < flowStep ? "flow-link done" : "flow-link"}>→</em>}</React.Fragment>; })}</div><div className="selection-flow-row">{flowNodes.slice(4).map((node, index) => { const actual = index + 4; return <React.Fragment key={node.title}><div className={flowClass(actual)}><span>{String(actual + 1).padStart(2, "0")}</span><div><b>{node.title}</b><small>{node.description}</small></div><i>{actual < flowStep ? "✓" : actual === flowStep && flowStatus === "running" ? "●" : ""}</i></div>{index < 2 && <em className={actual < flowStep ? "flow-link done" : "flow-link"}>→</em>}</React.Fragment>; })}</div></div>
        <div className="smart-section-title"><h2>今日选品推荐</h2><span>AI 衍生品 · 日本站推荐</span></div>
        <div className="smart-product-grid">{items.map((item) => <article key={String(pid(item))} className={selected && pid(selected) === pid(item) ? "smart-product selected" : "smart-product"} onClick={() => setSelected(item)}><div className="smart-image">{picture(item) ? <img src={picture(item)} loading="lazy" /> : <div className="image-empty">暂无图片</div>}</div><h3>{title(item)}</h3><div className="smart-product-bottom"><strong>{money(item)}</strong><span>销量 {Number(item.sales_count ?? item.supplier_sales_count ?? 0).toLocaleString()}</span></div></article>)}</div>{!items.length && <div className="empty-state">今日暂无推荐商品，请先完成商品衍生或稍后再试。</div>}
      </div>
      <aside className="smart-report"><h2>选品分析报告</h2>{selected ? <><div className="smart-report-product">{picture(selected) ? <img src={picture(selected)} /> : <div className="image-empty">暂无图片</div>}<div><h3>{title(selected)}</h3><strong>{money(selected)}</strong><p>销量 {Number(selected.sales_count ?? selected.supplier_sales_count ?? 0).toLocaleString()}</p><p>AI 参考分 {Number(selected.ai_score ?? selected.weighted_score ?? 0).toFixed(1)}</p></div></div><div className="smart-report-tabs"><button className={reportTab === "first" ? "active" : ""} onClick={() => setReportTab("first")}>选品分析 1-6</button><button className={reportTab === "last" ? "active" : ""} onClick={() => setReportTab("last")}>选品分析 7-8</button></div><div className="smart-dimensions">{visibleDimensions.map((name, index) => <div key={name}><span className="smart-dimension-icon">{index + 1}</span><div><b>{name}</b><small>{reportHas(selected, name) ? "已生成分析报告" : "暂无分析内容"}</small></div><strong>{reportHas(selected, name) ? "参考" : "-"}</strong></div>)}</div><div className="smart-report-actions"><button className="secondary" onClick={collect}>{isFavorite(selected) ? "★ 已在采集箱" : "☆ 加入采集箱"}</button><button className="primary" onClick={() => downloadReport(selected)}>⇩ 导出报告</button></div></> : <div className="empty-state">选择商品查看分析</div>}</aside>
    </div>
  </section>;
}

type AdminTab = "users" | "models" | "third" | "settings" | "releases";

function AdminConsole({ notice }: { notice: (s: string) => void }) {
  const tabs: Array<{ id: AdminTab; label: string }> = [{ id: "users", label: "用户管理" }, { id: "models", label: "模型配置" }, { id: "third", label: "第三方 API" }, { id: "settings", label: "业务配置" }, { id: "releases", label: "版本更新" }];
  const [tab, setTab] = useState<AdminTab>("users");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [releaseFile, setReleaseFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [releaseMeta, setReleaseMeta] = useState({ version: "", release_notes: "", force_update: false });

  async function load() {
    try {
      const data = tab === "users" ? await service.getUsers() : tab === "models" ? await service.getModelConfigs() : tab === "third" ? await service.getThirdPartyConfigs() : tab === "settings" ? await service.getSystemSettings() : await service.getAppReleases();
      setRows(Array.isArray(data) ? data as Record<string, unknown>[] : Object.entries(data).map(([key, value]) => ({ setting_key: key, setting_value: String(value ?? "") })));
    } catch (error) { notice(error instanceof Error ? error.message : "读取管理数据失败"); }
  }
  useEffect(() => { void load(); }, [tab]);
  function startEdit(row: Record<string, unknown> = {}) {
    setEditing(true);
    const base: Record<string, string> = row.id ? { id: String(row.id) } : {};
    if (tab === "users") setForm({ ...base, username: String(row.username || ""), password: "", real_name: String(row.real_name || ""), role: String(row.role || "student"), status: String(row.status ?? 1) });
    if (tab === "models") setForm({ ...base, config_name: String(row.config_name || ""), provider: String(row.provider || "custom"), model_type: String(row.model_type || "general"), base_url: String(row.base_url || ""), api_key_encrypted: String(row.api_key_encrypted || ""), model_name: String(row.model_name || ""), temperature: String(row.temperature ?? "0.2"), max_tokens: String(row.max_tokens ?? "4000"), status: String(row.status ?? 1), remark: String(row.remark || "") });
    if (tab === "third") setForm({ ...base, config_name: String(row.config_name || ""), service_type: String(row.service_type || "custom_api"), api_base_url: String(row.api_base_url || ""), access_key_encrypted: String(row.access_key_encrypted || ""), secret_key_encrypted: String(row.secret_key_encrypted || ""), db_host: String(row.db_host || ""), db_port: String(row.db_port || ""), db_name: String(row.db_name || ""), db_user: String(row.db_user || ""), db_password_encrypted: String(row.db_password_encrypted || ""), sign_name: String(row.sign_name || ""), template_code: String(row.template_code || ""), status: String(row.status ?? 1), remark: String(row.remark || "") });
    if (tab === "settings") setForm({ ...base, setting_key: String(row.setting_key || ""), setting_value: String(row.setting_value || "") });
  }
  function closeEdit() { setEditing(false); setForm({}); }
  async function save() {
    setBusy(true);
    try {
      const id = Number(form.id || 0);
      if (tab === "users") { const payload = { username: form.username, password: form.password || "123456", real_name: form.real_name, role: form.role, status: Number(form.status || 1) }; id ? await service.updateUser(id, payload) : await service.createUser(payload); }
      if (tab === "models") { const payload = { ...form, temperature: Number(form.temperature || 0.2), max_tokens: Number(form.max_tokens || 4000), status: Number(form.status || 1) }; id ? await service.updateModelConfig(id, payload) : await service.createModelConfig(payload); }
      if (tab === "third") { const payload = { ...form, db_port: form.db_port ? Number(form.db_port) : null, status: Number(form.status || 1) }; id ? await service.updateThirdPartyConfig(id, payload) : await service.createThirdPartyConfig(payload); }
      if (tab === "settings") await service.updateSystemSettings({ [form.setting_key]: form.setting_value });
      closeEdit(); await load(); notice("保存成功");
    } catch (error) { notice(error instanceof Error ? error.message : "保存失败"); } finally { setBusy(false); }
  }
  async function toggle(row: Record<string, unknown>) {
    const id = Number(row.id); const status = Number(row.status) === 1 ? 0 : 1;
    try { if (tab === "users") await service.setUserStatus(id, status); if (tab === "models") await service.setModelStatus(id, status); if (tab === "third") await service.setThirdPartyStatus(id, status); await load(); } catch (error) { notice(error instanceof Error ? error.message : "状态更新失败"); }
  }
  async function remove(row: Record<string, unknown>) {
    const id = Number(row.id); if (!id || !window.confirm("确定删除这条配置吗？")) return;
    try { if (tab === "users") await service.deleteUser(id); if (tab === "models") await service.deleteModelConfig(id); if (tab === "third") await service.deleteThirdPartyConfig(id); if (tab === "releases") await service.deleteAppRelease(id); await load(); notice("删除成功"); } catch (error) { notice(error instanceof Error ? error.message : "删除失败"); }
  }
  async function recharge(row: Record<string, unknown>) { const value = Number(window.prompt("请输入充值积分", "100") || 0); if (!value) return; try { await service.rechargeUser(Number(row.id), value, "管理员充值"); await load(); notice("充值成功"); } catch (error) { notice(error instanceof Error ? error.message : "充值失败"); } }
  async function testModel(row: Record<string, unknown>) { try { setBusy(true); const result = await service.testModelConfig(Number(row.id), "请用一句话介绍你自己"); notice(`模型测试完成：${String(result?.content || result?.answer || "已返回结果").slice(0, 80)}`); } catch (error) { notice(error instanceof Error ? error.message : "模型测试失败"); } finally { setBusy(false); } }
  async function uploadRelease() { if (!releaseFile || !releaseMeta.version) { notice("请填写版本号并选择安装包"); return; } try { setBusy(true); await service.uploadAppRelease({ ...releaseMeta, package: releaseFile }); setReleaseFile(null); setReleaseMeta({ version: "", release_notes: "", force_update: false }); await load(); notice("版本发布成功"); } catch (error) { notice(error instanceof Error ? error.message : "版本发布失败"); } finally { setBusy(false); } }
  function field(label: string, key: string, type = "text") { return <label className="admin-field">{label}<input type={type} value={form[key] || ""} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} /></label>; }
  const actionButtons = (row: Record<string, unknown>) => <div className="admin-actions"><button onClick={() => startEdit({ ...row, id: row.id })}>编辑</button>{["users", "models", "third"].includes(tab) && <button onClick={() => void toggle(row)}>{Number(row.status) === 1 ? "停用" : "启用"}</button>}{tab === "users" && <button onClick={() => void recharge(row)}>充值</button>}{tab === "models" && <button onClick={() => void testModel(row)}>测试</button>}{["users", "models", "third", "releases"].includes(tab) && <button className="danger-text" onClick={() => void remove(row)}>删除</button>}</div>;
  return <section className="admin-console"><div className="admin-console-head"><div><h2>系统管理</h2><p>集中管理账号、模型、第三方接口、业务阈值和版本发布。</p></div><button className="secondary" onClick={() => void load()}>刷新</button></div><div className="admin-tabs">{tabs.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => { setTab(item.id); closeEdit(); }}>{item.label}</button>)}</div>{tab === "releases" ? <div className="release-upload"><div><b>发布新版本</b><span>支持 .exe 或 .zip 安装包</span></div><input value={releaseMeta.version} onChange={(e) => setReleaseMeta((v) => ({ ...v, version: e.target.value }))} placeholder="版本号，例如 1.0.3" /><input value={releaseMeta.release_notes} onChange={(e) => setReleaseMeta((v) => ({ ...v, release_notes: e.target.value }))} placeholder="更新说明" /><input type="file" accept=".exe,.zip" onChange={(e) => setReleaseFile(e.target.files?.[0] || null)} /><label className="release-check"><input type="checkbox" checked={releaseMeta.force_update} onChange={(e) => setReleaseMeta((v) => ({ ...v, force_update: e.target.checked }))} /> 强制更新</label><button className="primary" disabled={busy} onClick={() => void uploadRelease()}>上传并发布</button></div> : <button className="primary admin-add" onClick={() => startEdit()}>＋ 新增{tabs.find((x) => x.id === tab)?.label}</button>}<div className="admin-table"><table><thead><tr><th>名称</th><th>类型</th><th>状态</th><th>信息</th><th>操作</th></tr></thead><tbody>{rows.map((row, index) => <tr key={String(row.id || index)}><td>{String(row.real_name || row.username || row.config_name || row.setting_name || row.version || row.setting_key || "-")}</td><td>{String(row.role || row.model_type || row.service_type || row.value_type || "-")}</td><td>{row.status === 1 || row.status === true ? "启用" : row.status === 0 || row.status === false ? "停用" : "-"}</td><td>{String(row.model_name || row.provider || row.filename || row.setting_value || row.release_notes || row.description || "-")}</td><td>{tab === "settings" ? <button onClick={() => startEdit(row)}>编辑</button> : actionButtons(row)}</td></tr>)}</tbody></table>{!rows.length && <div className="empty-state">暂无数据</div>}</div>{editing && <div className="admin-editor"><div className="admin-editor-head"><h3>{form.id ? "编辑配置" : "新增配置"}</h3><button onClick={closeEdit}>×</button></div><div className="admin-form-grid">{tab === "users" && <>{field("账号", "username")}{field("姓名", "real_name")}{field("初始密码", "password", "password")}<label className="admin-field">角色<select value={form.role || "student"} onChange={(e) => setForm((v) => ({ ...v, role: e.target.value }))}><option value="student">学生</option><option value="teacher">老师</option><option value="admin">管理员</option></select></label></>}{tab === "models" && <>{field("配置名称", "config_name")}{field("服务商", "provider")}{field("模型类型", "model_type")}{field("Base URL", "base_url")}{field("API Key", "api_key_encrypted", "password")}{field("模型名称", "model_name")}{field("温度", "temperature", "number")}{field("最大输出", "max_tokens", "number")}</>}{tab === "third" && <>{field("配置名称", "config_name")}{field("服务类型", "service_type")}{field("API Base URL", "api_base_url")}{field("Access Key", "access_key_encrypted", "password")}{field("Secret Key", "secret_key_encrypted", "password")}{field("签名名称", "sign_name")}{field("短信模板", "template_code")}{field("数据库地址", "db_host")}{field("数据库端口", "db_port", "number")}</>}{tab === "settings" && <>{field("配置键", "setting_key")}{field("配置值", "setting_value")}</>}</div><div className="admin-editor-actions"><button className="secondary" onClick={closeEdit}>取消</button><button className="primary" disabled={busy} onClick={() => void save()}>保存</button></div></div>}</section>;
}

type ThemeState = { font: string; size: string; background: string; opacity: string };

const themeOptions = {
  fonts: [
    { value: "Microsoft YaHei UI", label: "微软雅黑 UI" },
    { value: "Microsoft YaHei", label: "微软雅黑" },
    { value: "Segoe UI", label: "Segoe UI" },
    { value: "Arial", label: "Arial" },
  ],
  sizes: [
    { value: "13px", label: "小号 13px" },
    { value: "14px", label: "标准 14px" },
    { value: "15px", label: "大号 15px" },
    { value: "16px", label: "特大 16px" },
  ],
  backgrounds: [
    { value: "background.png", label: "星空晨曦" },
    { value: "theme-anime.jpg", label: "黑红幻想" },
    { value: "theme-orange.jpg", label: "橙色流体" },
    { value: "theme-mountain.png", label: "雪山旷野" },
    { value: "theme-stars.png", label: "星星蓝幕" },
  ],
};

function applyTheme(theme: ThemeState) {
  const root = document.documentElement;
  root.style.setProperty("--user-font", theme.font);
  root.style.setProperty("--user-font-size", theme.size);
  root.style.setProperty("--ui-transparency", theme.opacity || "0.30");
  document.body.style.backgroundImage = `linear-gradient(rgba(234, 241, 245, 0.48), rgba(234, 241, 245, 0.48)), url(\"${theme.background}\")`;
}

function ThemeSettings() {
  const [theme, setTheme] = useState<ThemeState>(() => {
    try {
      return { font: "Microsoft YaHei UI", size: "14px", background: "background.png", opacity: "0.30", ...JSON.parse(localStorage.getItem("tk_theme") || "{}") };
    } catch { return { font: "Microsoft YaHei UI", size: "14px", background: "background.png", opacity: "0.30" }; }
  });
  const [dragging, setDragging] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => { applyTheme(theme); }, [theme]);
  function update(key: keyof ThemeState, value: string) {
    const next = { ...theme, [key]: value };
    setTheme(next);
    localStorage.setItem("tk_theme", JSON.stringify(next));
  }
  async function useBackground(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setUploadStatus("请选择图片文件");
      return;
    }
    setUploadStatus("正在处理图片...");
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("图片读取失败"));
        reader.onload = () => {
          const image = new Image();
          image.onerror = () => reject(new Error("图片解析失败"));
          image.onload = () => {
            const maxSide = 1920;
            const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
            canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
            const context = canvas.getContext("2d");
            if (!context) return reject(new Error("图片处理失败"));
            context.fillStyle = "#edf3f5";
            context.fillRect(0, 0, canvas.width, canvas.height);
            context.drawImage(image, 0, 0, canvas.width, canvas.height);
            resolve(canvas.toDataURL("image/jpeg", 0.86));
          };
          image.src = String(reader.result);
        };
        reader.readAsDataURL(file);
      });
      update("background", dataUrl);
      setUploadStatus("已应用自定义背景");
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "图片处理失败");
    }
  }
  function onDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void useBackground(event.dataTransfer.files?.[0]);
  }
  const hasCustomBackground = theme.background.startsWith("data:image/");
  return <section className="theme-settings">
    <div className="theme-settings-heading"><div><h2>软件换肤</h2><p>调整字体、字号和软件背景，修改会即时生效。</p></div><span className="theme-preview-dot" /></div>
    <div className="theme-setting-grid">
      <label>字体<select value={theme.font} onChange={(e) => update("font", e.target.value)}>{themeOptions.fonts.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>字号<select value={theme.size} onChange={(e) => update("size", e.target.value)}>{themeOptions.sizes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>背景图<select value={theme.background} onChange={(e) => update("background", e.target.value)}>{themeOptions.backgrounds.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}{hasCustomBackground && <option value={theme.background}>自定义背景图</option>}</select></label>
    </div>
    <div className={dragging ? "theme-upload is-dragging" : "theme-upload"} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }} onDrop={onDrop}>
      <span className="theme-upload-icon">▧</span>
      <div><b>上传自定义背景图</b><p>点击选择图片，或将图片拖到这里自动换肤</p></div>
      <button type="button" className="secondary" onClick={() => fileInput.current?.click()}>选择图片</button>
      <input ref={fileInput} type="file" accept="image/*" hidden onChange={(event) => { void useBackground(event.target.files?.[0]); event.currentTarget.value = ""; }} />
    </div>
    {uploadStatus && <p className="theme-upload-status">{uploadStatus}</p>}
  </section>;
}

function AboutPage() {
  return <section className="about-page"><div className="about-card"><div className="about-mark">TK</div><div><h2>益行跨境 AI 平台</h2><p>TikTok 日本选品专家</p><span>跨境商品分析、AI 选品、1688 匹配与视频内容工作台</span></div></div><div className="about-card about-info"><h3>平台信息</h3><div><span>当前客户端</span><b>Electron 桌面版</b></div><div><span>服务范围</span><b>商品选品 · 供应链匹配 · 内容生成</b></div><div><span>数据服务</span><b>FastMoss · 1688 · 妙手</b></div></div></section>;
}

function Products2({ page, rows, selected, onSelect, onCollect, onSync, regions, rankRegion, rankList, rankCategory, rankStart, rankEnd, categories, onRankChange }: { page: Page; rows: Product[]; selected: Product | null; onSelect: (p: Product) => void; onCollect: (p: Product) => void; onSync?: () => void; regions: Array<{ region_name?: string; region_code?: string }>; rankRegion: string; rankList: string; rankCategory: string; rankStart: string; rankEnd: string; categories: string[]; onRankChange: (key: string, value: string) => void }) {
  useEffect(() => {
    if (page === "favorites") {
      document.querySelectorAll<HTMLButtonElement>(".favorite-list .list-action").forEach((button) => { button.textContent = "移除"; });
      return;
    }
    if (page === "rank") {
      document.querySelectorAll<HTMLButtonElement>(".products .product > button").forEach((button, index) => { button.textContent = rows[index]?.derived_count ? "查看衍生品" : "可以衍生"; });
    }
    if (page !== "rank" || (JSON.parse(localStorage.getItem("tk_electron_user") || "null")?.role !== "admin")) return;
    const heading = document.querySelector(".products .section-heading");
    if (!heading || heading.querySelector(".rank-sync-button")) return;
    const button = document.createElement("button");
    button.className = "primary rank-sync-button";
    button.textContent = "同步新品榜单";
    button.onclick = async () => { button.disabled = true; button.textContent = "同步中..."; try { await service.syncConfiguredRanks(); window.location.reload(); } catch { button.disabled = false; button.textContent = "同步新品榜单"; } };
    heading.appendChild(button);
    return () => { button.remove(); };
  }, [page]);
  if (page === "favorites") return <section className="favorites-page"><div className="section-heading"><div><h2>采集箱</h2><p>已保存的商品快照与货源信息</p></div></div><div className="favorite-list"><div className="favorite-list-head"><span>商品信息</span><span>来源</span><span>国家/地区</span><span>商品分类</span><span>价格</span><span>销量</span><span>1688 链接</span><span>操作</span></div>{rows.map((item) => <div className="favorite-list-row" key={String(pid(item))}><div className="favorite-product"><div className="favorite-thumb">{picture(item) ? <img src={picture(item)} /> : <span>暂无图片</span>}</div><div><b>{title(item)}</b><small>{item.source_type || "商品快照"}</small></div></div><span>{String(item.source_type || "-" )}</span><span>{String(item.region || "-" )}</span><span>{String(item.category || "未分类")}</span><strong>{money(item)}</strong><span>{Number(item.sales_count ?? item.supplier_sales_count ?? 0).toLocaleString()}</span>{(item as Product & { supplier_url?: string; detail_url?: string }).supplier_url || (item as Product & { detail_url?: string }).detail_url ? <a className="supplier-link" href={(item as Product & { supplier_url?: string; detail_url?: string }).supplier_url || (item as Product & { detail_url?: string }).detail_url} target="_blank" rel="noreferrer">打开链接</a> : <span className="supplier-link disabled">匹配 1688</span>}<button className="list-action" onClick={() => onCollect(item)}>查看详情</button></div>)}{!rows.length && <div className="empty-state">暂无采集商品</div>}</div></section>;
  const regionLabel = regions.find((item) => item.region_code === rankRegion)?.region_name || rankRegion;
  return <div className="workspace"><section className="products"><div className="rank-filters"><div className="rank-filter-line"><b>上架时间</b><input type="date" value={rankStart} onChange={(e) => onRankChange("start", e.target.value)} /><span>至</span><input type="date" value={rankEnd} onChange={(e) => onRankChange("end", e.target.value)} /></div><div className="rank-filter-line"><b>国家/地区</b><button className={rankRegion === "ALL" ? "active" : ""} onClick={() => onRankChange("region", "ALL")}>全部</button>{regions.map((item) => <button key={item.region_code} className={rankRegion === item.region_code ? "active" : ""} onClick={() => onRankChange("region", String(item.region_code || ""))}>{item.region_name || item.region_code}</button>)}</div><div className="rank-filter-line"><b>商品分类</b><button className={!rankCategory ? "active" : ""} onClick={() => onRankChange("category", "")}>全部</button>{categories.map((item) => <button key={item} className={rankCategory === item ? "active" : ""} onClick={() => onRankChange("category", item)}>{item}</button>)}</div><div className="rank-filter-line"><b>商品榜单</b>{[{ value: "sales", label: "销量榜" }, { value: "new", label: "新品榜" }, { value: "hot", label: "热销榜" }].map((item) => <button key={item.value} className={rankList === item.value ? "active" : ""} onClick={() => onRankChange("list", item.value)}>{item.label}</button>)}</div></div><div className="section-heading"><div><h2>{rankList === "sales" ? "销量榜" : rankList === "hot" ? "热销榜" : "新品榜单"}</h2><p>{regionLabel} · {rows.length} 个商品</p></div></div><div className="product-grid">{rows.map((p) => <article className={selected && pid(selected) === pid(p) ? "product selected" : "product"} key={String(pid(p))} onClick={() => onSelect(p)}><div className="image-wrap">{picture(p) ? <img src={picture(p)} loading="lazy" /> : <div className="image-empty">暂无图片</div>}</div><h3>{title(p)}</h3><div className="product-tag">{p.category || p.source_type || "商品"}</div><div className="product-meta"><strong>{money(p)}</strong><span>销量 {Number(p.sales_count ?? p.supplier_sales_count ?? 0).toLocaleString()}</span></div><button className="primary" onClick={(e) => { e.stopPropagation(); onCollect(p); }}>加入采集箱</button></article>)}</div>{!rows.length && <div className="empty-state">暂无数据</div>}</section><aside className="report"><h2>选品分析报告</h2>{selected ? <><div className="report-product">{picture(selected) ? <img src={picture(selected)} /> : <div className="image-empty">暂无图片</div>}<div><h3>{title(selected)}</h3><strong>{money(selected)}</strong><p>销量 {Number(selected.sales_count ?? selected.supplier_sales_count ?? 0).toLocaleString()}</p><p>AI 参考分 {Number(selected.ai_score ?? selected.weighted_score ?? 0).toFixed(1)}</p></div></div><button className="primary full" onClick={() => onCollect(selected)}>加入采集箱</button></> : <div className="empty-state">请选择商品</div>}</aside></div>;
}

function App2Clean() {
  const stored = localStorage.getItem("tk_electron_user");
  const [user, setUser] = useState<User | null>(() => { if (!stored) return null; const parsed = JSON.parse(stored) as User; return { ...parsed, credits: parsed.credits ?? parsed.credit_balance ?? 0 }; });
  const [page, setPage] = useState<Page>("studio");
  const [rows, setRows] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [regions, setRegions] = useState<Array<{ region_name?: string; region_code?: string }>>([]);
  const [rankRegion, setRankRegion] = useState("JP");
  const [rankList, setRankList] = useState("new");
  const [rankCategory, setRankCategory] = useState("");
  const [rankStart, setRankStart] = useState("");
  const [rankEnd, setRankEnd] = useState("");
  const [notice, setNotice] = useState("");
  const allowed = useMemo(() => menus.filter((m) => m.roles.includes(user?.role || "student")), [user]);
  const flash = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(""), 3000); };
  const load = async (next: Page) => {
    if (!["library", "rank", "favorites"].includes(next)) return;
    try {
      const data = next === "library" ? await service.getLibrary() : next === "favorites" ? await service.getFavorites() : await service.getRanks({ region: rankRegion, list_type: rankList, category: rankCategory, start_date: rankStart, end_date: rankEnd, page: 1, pagesize: 50, paged: true });
      const list = Array.isArray(data) ? data : (data as { items?: Product[] })?.items || [];
      const normalized = list.map((item) => ({ ...item, category: categoryLabel(item.category) }));
      setRows(normalized); setSelected(normalized[0] || null);
    } catch (e) { flash(e instanceof Error ? e.message : "读取数据失败"); }
  };
  useEffect(() => { if (user) { service.getRegions().then((items) => setRegions(items.length ? items : DEFAULT_REGIONS)).catch(() => setRegions(DEFAULT_REGIONS)); } }, [user]);
  useEffect(() => { if (user) load(page); }, [user, page, rankRegion, rankList, rankCategory, rankStart, rankEnd]);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("tk_theme") || "{}");
      applyTheme({ font: "Microsoft YaHei UI", size: "14px", background: "background.png", opacity: "0.30", ...saved });
    } catch { applyTheme({ font: "Microsoft YaHei UI", size: "14px", background: "background.png", opacity: "0.30" }); }
  }, []);
  if (!user) return <><WindowTitlebar /><Login done={setUser} /></>;
  const collect = async (product: Product) => { try { if (page === "favorites" && product.id) { await service.removeFavorite(product.id); await load("favorites"); flash("已从采集箱移除"); } else if (page === "rank" && product.id && !product.derived_count) { await service.generateDerived(product.id); flash("已开始生成衍生品"); } else { await service.collect(product); flash("已加入采集箱"); } } catch (e) { flash(e instanceof Error ? e.message : "操作失败"); } };
  const categories = Array.from(new Set(rows.map((item) => categoryLabel(item.category)).filter(Boolean)));
  const onRankChange = (key: string, value: string) => { if (key === "region") setRankRegion(value); if (key === "list") setRankList(value); if (key === "category") setRankCategory(value); if (key === "start") setRankStart(value); if (key === "end") setRankEnd(value); };
  return <><WindowTitlebar /><div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">TK</div><div><b>益行跨境 AI 平台</b><span>TikTok 日本选品专家</span></div></div><nav>{allowed.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><i>{item.icon}</i>{item.label}</button>)}</nav><div className="account"><div className="avatar">{(user.real_name || user.username || "A").slice(0, 1)}</div><div className="account-copy"><b>{user.real_name || user.username}</b><span>{user.role} · 积分 {user.credits ?? user.credit_balance ?? 0}</span></div><button className="logout" onClick={() => { service.logout(); setUser(null); }}>退出登录</button></div></aside><main className="main">{page === "studio" && <SmartSelection user={user} onNotice={flash} onOpenLibrary={() => setPage("library")} onCreditChange={(credits) => setUser((current) => current ? { ...current, credits } : current)} />}{page === "library" && <LibraryPage rows={rows} onNotice={flash} />}{["rank", "favorites"].includes(page) && <Products2 page={page} rows={rows} selected={selected} onSelect={setSelected} onCollect={collect} regions={regions} rankRegion={rankRegion} rankList={rankList} rankCategory={rankCategory} rankStart={rankStart} rankEnd={rankEnd} categories={categories} onRankChange={onRankChange} />}{page === "dashboard" && <Dashboard />}{page === "store" && <StorePage user={user} notice={flash} onCreditChange={(credits) => setUser((current) => current ? { ...current, credits } : current)} />}{page === "video" && <VideoPage user={user} notice={flash} onCreditChange={(credits) => setUser((current) => current ? { ...current, credits } : current)} />}{page === "profile" && <><Profile user={user} onNotice={flash} onCreditChange={(credits) => setUser((current) => current ? { ...current, credits } : current)} /><ThemeSettings /></>}{page === "teacher" && <Teacher notice={flash} />}{page === "about" && <AboutPage />}{page === "admin" && <AdminConsole notice={flash} />}{notice && <div className="toast">{notice}</div>}</main></div></>;
}

export default App2Clean;
