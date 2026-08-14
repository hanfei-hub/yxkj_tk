import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Product, Role, User, VideoProject } from "./types";
import * as service from "./api";
import "./migrated.css";

type Page =
  | "studio"
  | "library"
  | "rank"
  | "favorites"
  | "teacher"
  | "dashboard"
  | "store"
  | "video"
  | "profile"
  | "about"
  | "admin";
const legacySelectionFlowLabels = [
  "步骤 1：AI 对话挖掘潜力爆品",
  "步骤 2：智能匹配优质供应链",
  "步骤 3：全网数据拓品，摸清市场全貌",
  "步骤 4：多维风控过滤，规避全部运营雷区",
  "步骤 5：热销竞品规避，抢占蓝海赛道",
  "步骤 6：自动生成专业可视化选品报告",
  "步骤 7：输出最终精选 10 款优质爆品",
];
/* 统一描边 SVG 图标集（高级简约，currentColor 继承，激活态自动变金） */
const ICON_PATHS: Record<string, React.ReactNode> = {
  studio: (
    <>
      <path d="M12 3l1.7 4.6L18 9l-4.3 1.4L12 15l-1.7-4.6L6 9l4.3-1.4z" />
      <path d="M19 14l.8 2.3L22 17l-2.2.7L19 20l-.8-2.3L16 17l2.2-.7z" />
    </>
  ),
  library: (
    <>
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </>
  ),
  rank: (
    <>
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="M7 4h10v5a5 5 0 0 1-10 0V4z" />
      <path d="M7 4H4v2a3 3 0 0 0 3 3" />
      <path d="M17 4h3v2a3 3 0 0 1-3 3" />
    </>
  ),
  favorites: (
    <polygon points="12 2 15.1 8.6 22 9.3 17 14 18.2 21 12 17.6 5.8 21 7 14 2 9.3 8.9 8.6 12 2" />
  ),
  teacher: (
    <>
      <path d="M22 10L12 5 2 10l10 5 10-5z" />
      <path d="M6 12v5c0 1 2.7 2.5 6 2.5s6-1.5 6-2.5v-5" />
    </>
  ),
  dashboard: (
    <>
      <line x1="5" y1="20" x2="5" y2="12" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="19" y1="20" x2="19" y2="9" />
    </>
  ),
  store: (
    <>
      <path d="M6 7h12l-1 13H7L6 7z" />
      <path d="M9 7a3 3 0 0 1 6 0" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="M16 10l5-3v10l-5-3z" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
    </>
  ),
  about: (
    <>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16" />
      <line x1="12" y1="8" x2="12" y2="8.01" />
    </>
  ),
  admin: (
    <>
      <line x1="4" y1="7" x2="20" y2="7" />
      <circle cx="9" cy="7" r="2.4" />
      <line x1="4" y1="17" x2="20" y2="17" />
      <circle cx="15" cy="17" r="2.4" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="8" cy="12" r="2.4" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <path d="M21 16l-5-5L5 20" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.1.9-1.1 1.8" />
      <line x1="12" y1="17" x2="12" y2="17.01" />
    </>
  ),
  bell: (
    <>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
    </>
  ),
  minimize: <line x1="5" y1="12" x2="19" y2="12" />,
  maximize: <rect x="5" y="5" width="14" height="14" rx="2" />,
  close: (
    <>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </>
  ),
  dot: <circle cx="12" cy="12" r="3" />,
};
function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name] || ICON_PATHS.dot}
    </svg>
  );
}

const menus: Array<{
  id: Page;
  label: string;
  icon: string;
  roles: Role[];
  group: string;
}> = [
  {
    id: "studio",
    label: "智能选品",
    icon: "studio",
    roles: ["admin", "teacher", "student"],
    group: "选品工作台",
  },
  {
    id: "library",
    label: "选品库",
    icon: "library",
    roles: ["admin", "student"],
    group: "选品工作台",
  },
  {
    id: "rank",
    label: "新品榜单",
    icon: "rank",
    roles: ["admin", "teacher", "student"],
    group: "选品工作台",
  },
  {
    id: "dashboard",
    label: "数据看板",
    icon: "dashboard",
    roles: ["admin", "teacher"],
    group: "内容与创作",
  },
  {
    id: "video",
    label: "视频生成",
    icon: "video",
    roles: ["admin", "teacher", "student"],
    group: "内容与创作",
  },
  {
    id: "store",
    label: "店铺管理",
    icon: "store",
    roles: ["admin", "teacher", "student"],
    group: "数据资产",
  },
  {
    id: "teacher",
    label: "教师看板",
    icon: "teacher",
    roles: ["admin", "teacher"],
    group: "数据资产",
  },
  {
    id: "profile",
    label: "个人中心",
    icon: "profile",
    roles: ["admin", "teacher", "student"],
    group: "账户",
  },
  {
    id: "about",
    label: "关于益行",
    icon: "about",
    roles: ["admin", "teacher", "student"],
    group: "账户",
  },
  {
    id: "admin",
    label: "系统管理",
    icon: "admin",
    roles: ["admin"],
    group: "系统",
  },
];
function title(p: Product) {
  return p.title || p.derived_title || "未命名商品";
}
function picture(p: Product) {
  const snapshot = p.product_snapshot || {};
  return (
    p.image_url ||
    p.supplier_image_url ||
    String(
      snapshot.image_url ||
        snapshot.supplier_image_url ||
        snapshot.pic_url ||
        "",
    )
  );
}
function supplierUrl(p: Product) {
  const snapshot = p.product_snapshot || {};
  return (
    p.supplier_source_url ||
    String(
      snapshot.supplier_source_url ||
        snapshot.source_url ||
        snapshot.detail_url ||
        (snapshot.supplier_product_id
          ? `https://detail.1688.com/offer/${snapshot.supplier_product_id}.html`
          : ""),
    )
  );
}
const FIXED_CATEGORIES = [
  "全部",
  "美妆个护",
  "女装与女士内衣",
  "时尚配件",
  "运动与户外",
  "手机与数码",
  "居家日用",
  "汽车与摩托车",
  "男装与男士内衣",
  "玩具和爱好",
  "厨房用品",
  "家装建材",
  "电脑办公",
  "箱包",
  "鞋靴",
  "五金工具",
  "家纺布艺",
  "家电",
  "宠物用品",
  "珠宝与衍生品",
  "母婴用品",
  "家具",
  "儿童时尚",
];
const FIXED_COUNTRIES: Array<{ code: string; name: string; isNew?: boolean }> = [
  { code: "US", name: "美国" },
  { code: "JP", name: "日本" },
  { code: "MY", name: "马来西亚", isNew: true },
  { code: "VN", name: "越南" },
  { code: "TH", name: "泰国" },
  { code: "SG", name: "新加坡", isNew: true },
  { code: "PH", name: "菲律宾" },
];

function RegionFilterRow({
  value,
  onChange,
  expanded,
  onToggleExpand,
}: {
  value: string;
  onChange: (v: string) => void;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const firstRow = [{ code: "ALL", name: "全部" }, ...FIXED_COUNTRIES.slice(0, 4)];
  const secondRow = FIXED_COUNTRIES.slice(4);
  const renderChip = (item: (typeof FIXED_COUNTRIES)[0] | { code: string; name: string }) => (
    <button
      key={item.code}
      className={value === item.code ? "active" : ""}
      onClick={() => onChange(item.code)}
    >
      {item.name}
      {"isNew" in item && item.isNew && <em className="new-badge">NEW</em>}
    </button>
  );
  return (
    <div className="filter-row">
      <span className="filter-label">国家/地区：</span>
      <div className="filter-chips">{firstRow.map(renderChip)}</div>
      {secondRow.length > 0 && (
        <button
          type="button"
          className="filter-toggle"
          onClick={onToggleExpand}
          aria-expanded={expanded}
        >
          {expanded ? "收起" : "展开"}
          <span className={expanded ? "chevron-up" : "chevron-down"}>⌄</span>
        </button>
      )}
      {expanded && secondRow.length > 0 && (
        <div className="filter-chips filter-chips-more">{secondRow.map(renderChip)}</div>
      )}
    </div>
  );
}

function CategoryFilterRow({
  options,
  value,
  onChange,
  expanded,
  onToggleExpand,
  allValue = "ALL",
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  expanded: boolean;
  onToggleExpand: () => void;
  allValue?: string;
}) {
  const first = options[0] || "全部";
  const rest = options.slice(1);
  const firstRowCount = 8;
  const firstRow = [first, ...rest.slice(0, firstRowCount - 1)];
  const secondRow = rest.slice(firstRowCount - 1);
  return (
    <div className="filter-row">
      <span className="filter-label">商品分类：</span>
      <div className="filter-chips">
        {firstRow.map((item) => (
          <button
            key={item}
            className={value === (item === first ? allValue : item) ? "active" : ""}
            onClick={() => onChange(item === first ? allValue : item)}
          >
            {item}
          </button>
        ))}
      </div>
      {secondRow.length > 0 && (
        <button
          type="button"
          className="filter-toggle"
          onClick={onToggleExpand}
          aria-expanded={expanded}
        >
          {expanded ? "收起" : "展开"}
          <span className={expanded ? "chevron-up" : "chevron-down"}>⌄</span>
        </button>
      )}
      {expanded && secondRow.length > 0 && (
        <div className="filter-chips filter-chips-more">
          {secondRow.map((item) => (
            <button
              key={item}
              className={value === item ? "active" : ""}
              onClick={() => onChange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function categoryLabel(value?: string) {
  return String(value || "").trim() || "未分类";
}
function productSourceLabel(item: Product) {
  return (
    (
      {
        derived: "衍生品",
        new_product: "新品榜",
        ai_search: "AI搜索",
      } as Record<string, string>
    )[String(item.source_type || "").toLowerCase()] ||
    (item.list_type ? "新品榜" : "商品快照")
  );
}
function regionLabel(value?: string) {
  return value || "未标注";
}
function money(p: Product) {
  const n = Number(p.price ?? p.supplier_price ?? 0);
  const currency = String(p.currency || "").toUpperCase();
  const symbol =
    ["CNY", "RMB", "YUAN"].includes(currency) || p.region === "CN"
      ? "¥"
      : currency === "JPY" || p.region === "JP"
        ? "円"
        : "$";
  return `${symbol}${n.toFixed(2)}`;
}
function pid(p: Product) {
  return p.id ?? p.source_product_id ?? title(p);
}

function Login({ done }: { done: (u: User) => void }) {
  const [mode, setMode] = useState<"account" | "phone">("account");
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [seconds, setSeconds] = useState(0);
  async function sendCode() {
    if (!phone.trim()) {
      setError("请输入手机号");
      return;
    }
    setSending(true);
    setError("");
    try {
      await service.smsSendCode(phone.trim());
      setSeconds(60);
      const timer = window.setInterval(
        () =>
          setSeconds((value) => {
            if (value <= 1) {
              window.clearInterval(timer);
              return 0;
            }
            return value - 1;
          }),
        1000,
      );
    } catch (x) {
      setError(x instanceof Error ? x.message : "验证码发送失败");
    } finally {
      setSending(false);
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      done(
        mode === "account"
          ? await service.login(account, password)
          : await service.smsLogin(phone.trim(), code.trim()),
      );
    } catch (x) {
      setError(x instanceof Error ? x.message : "登录失败");
    }
  }
  return (
    <div className="login-page">
      <div className="login-visual">
        <div className="brand-mark large">TK</div>
        <h1>益行跨境 AI 平台</h1>
        <p>TikTok 日本市场智能选品工作台</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <h2>欢迎回来</h2>
        <div className="login-tabs">
          <button
            type="button"
            className={mode === "phone" ? "active" : ""}
            onClick={() => {
              setMode("phone");
              setError("");
            }}
          >
            手机验证码登录
          </button>
          <button
            type="button"
            className={mode === "account" ? "active" : ""}
            onClick={() => {
              setMode("account");
              setError("");
            }}
          >
            账号密码登录
          </button>
        </div>
        {mode === "account" ? (
          <>
            <label>
              账号
              <input
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                required
              />
            </label>
            <label>
              密码
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          </>
        ) : (
          <>
            <label>
              手机号
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="请输入手机号"
                required
              />
            </label>
            <label>
              验证码
              <div className="code-input">
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="请输入短信验证码"
                  required
                />
                <button
                  type="button"
                  onClick={() => void sendCode()}
                  disabled={sending || seconds > 0}
                >
                  {seconds
                    ? `${seconds}s 后重发`
                    : sending
                      ? "发送中..."
                      : "获取验证码"}
                </button>
              </div>
            </label>
          </>
        )}
        {error && <div className="error">{error}</div>}
        <button className="primary">登录</button>
        <small className="login-tip">手机号首次登录会自动创建学生账号</small>
      </form>
    </div>
  );
}

function Products({
  page,
  rows,
  onSelect,
  selected,
  onCollect,
}: {
  page: Page;
  rows: Product[];
  onSelect: (p: Product) => void;
  selected: Product | null;
  onCollect: (p: Product) => void;
}) {
  return (
    <div className="workspace">
      <section className="products">
        <div className="section-heading">
          <div>
            <h2>
              {page === "library"
                ? "选品库"
                : page === "favorites"
                  ? "采集箱"
                  : "新品榜单"}
            </h2>
            <p>{rows.length} 个商品</p>
          </div>
        </div>
        <div className="product-grid">
          {rows.map((p) => (
            <article
              className={
                selected && pid(selected) === pid(p)
                  ? "product selected"
                  : "product"
              }
              key={String(pid(p))}
              onClick={() => onSelect(p)}
            >
              <div className="image-wrap">
                {picture(p) ? (
                  <img src={picture(p)} loading="lazy" />
                ) : (
                  <div className="image-empty">暂无图片</div>
                )}
              </div>
              <h3>{title(p)}</h3>
              <div className="product-tag">
                {p.source_type || p.category || "商品"}
              </div>
              <div className="product-meta">
                <strong>{money(p)}</strong>
                <span>
                  销量{" "}
                  {Number(
                    p.sales_count ?? p.supplier_sales_count ?? 0,
                  ).toLocaleString()}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCollect(p);
                }}
              >
                加入采集箱
              </button>
            </article>
          ))}
        </div>
        {!rows.length && <div className="empty-state">暂无数据</div>}
      </section>
      <aside className="report">
        <h2>选品分析报告</h2>
        {selected ? (
          <>
            <div className="report-product">
              {picture(selected) ? (
                <img src={picture(selected)} />
              ) : (
                <div className="image-empty">暂无图片</div>
              )}
              <div>
                <h3>{title(selected)}</h3>
                <strong>{money(selected)}</strong>
                <p>请从详情页查看完整分析</p>
              </div>
            </div>
            <button
              className="primary full"
              onClick={() => onCollect(selected)}
            >
              加入采集箱
            </button>
          </>
        ) : (
          <div className="empty-state">请选择商品</div>
        )}
      </aside>
    </div>
  );
}

function Teacher({ notice }: { notice: (s: string) => void }) {
  const [sources, setSources] = useState<Product[]>([]);
  const [source, setSource] = useState<Product | null>(null);
  const [derived, setDerived] = useState<Product[]>([]);
  useEffect(() => {
    service
      .getTeacherProducts()
      .then((list) => {
        const preferredId = localStorage.getItem("tk_rank_derived_source_id");
        const preferred = preferredId
          ? list.find((item) => String(pid(item)) === preferredId)
          : null;
        setSources(list);
        setSource(preferred || list[0] || null);
        localStorage.removeItem("tk_rank_derived_source_id");
      })
      .catch((e) =>
        notice(e instanceof Error ? e.message : "读取教师看板失败"),
      );
  }, []);
  useEffect(() => {
    if (source)
      service
        .getTeacherDerived(pid(source))
        .then(setDerived)
        .catch((e) =>
          notice(e instanceof Error ? e.message : "读取衍生品失败"),
        );
  }, [source]);
  async function approve(p: Product) {
    try {
      await service.approveDerived(pid(p));
      setDerived((rows) => rows.filter((x) => pid(x) !== pid(p)));
      notice("已通过审核");
    } catch (e) {
      notice(e instanceof Error ? e.message : "审核失败");
    }
  }
  async function reject(p: Product) {
    try {
      await service.rejectDerived(pid(p), [], "教师审核拒绝");
      setDerived((rows) => rows.filter((x) => pid(x) !== pid(p)));
      notice("已拒绝");
    } catch (e) {
      notice(e instanceof Error ? e.message : "拒绝失败");
    }
  }
  return (
    <section className="teacher-workspace">
      <div className="teacher-sources">
        <h2>教师看板</h2>
        <p>选择原商品查看衍生品</p>
        <div className="source-grid">
          {sources.map((p) => (
            <button
              className={
                source && pid(source) === pid(p)
                  ? "source-card active"
                  : "source-card"
              }
              key={String(pid(p))}
              onClick={() => setSource(p)}
            >
              {picture(p) ? (
                <img src={picture(p)} />
              ) : (
                <span className="image-empty">暂无图片</span>
              )}
              <b>{title(p)}</b>
              <small>{p.derived_count ?? 0} 个衍生品</small>
            </button>
          ))}
        </div>
      </div>
      <div className="review-list">
        <h2>衍生品审核</h2>
        {derived.map((p) => (
          <article className="review-card" key={String(pid(p))}>
            <div className="review-head">
              {picture(p) ? (
                <img src={picture(p)} />
              ) : (
                <div className="image-empty">暂无图片</div>
              )}
              <div>
                <h3>{title(p)}</h3>
                <span>{money(p)}</span>
              </div>
              <div className="review-actions">
                <button className="success" onClick={() => approve(p)}>
                  通过
                </button>
                <button className="danger" onClick={() => reject(p)}>
                  拒绝
                </button>
              </div>
            </div>
          </article>
        ))}
        {!derived.length && <div className="empty-state">暂无待审核衍生品</div>}
      </div>
    </section>
  );
}

function Admin({ notice }: { notice: (s: string) => void }) {
  const [tab, setTab] = useState("users");
  const [rows, setRows] = useState<unknown[]>([]);
  useEffect(() => {
    const task =
      tab === "users"
        ? service.getUsers()
        : tab === "models"
          ? service.getModelConfigs()
          : tab === "third"
            ? service.getThirdPartyConfigs()
            : tab === "settings"
              ? service.getSystemSettings()
              : service.getAppReleases();
    task
      .then((data) =>
        setRows(
          Array.isArray(data)
            ? data
            : Object.entries(data).map(([key, value]) => ({ key, value })),
        ),
      )
      .catch((e) =>
        notice(e instanceof Error ? e.message : "读取系统管理失败"),
      );
  }, [tab]);
  const tabs = [
    { id: "users", label: "用户管理" },
    { id: "models", label: "模型配置" },
    { id: "third", label: "第三方 API" },
    { id: "settings", label: "业务配置" },
    { id: "releases", label: "版本更新" },
  ];
  return (
    <section className="admin-page">
      <div className="admin-tabs">
        {tabs.map((x) => (
          <button
            className={tab === x.id ? "active" : ""}
            key={x.id}
            onClick={() => setTab(x.id)}
          >
            {x.label}
          </button>
        ))}
      </div>
      <div className="admin-table">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>状态</th>
              <th>信息</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const x = row as Record<string, unknown>;
              return (
                <tr key={i}>
                  <td>
                    {String(
                      x.real_name ||
                        x.username ||
                        x.config_name ||
                        x.key ||
                        x.version ||
                        "-",
                    )}
                  </td>
                  <td>
                    {String(x.role || x.model_type || x.service_type || "-")}
                  </td>
                  <td>{x.status === 1 || x.status === true ? "启用" : "-"}</td>
                  <td>
                    {String(
                      x.model_name ||
                        x.provider ||
                        x.filename ||
                        x.value ||
                        x.release_notes ||
                        "-",
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!rows.length && <div className="empty-state">暂无数据</div>}
      </div>
    </section>
  );
}

function Studio({
  search,
}: {
  search: (message: string, count: number) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  return (
    <section className="studio">
      <div className="studio-intro">
        <div>
          <em>✦</em>
          <h2>告诉我您想找什么样的产品？</h2>
          <p>例如：最近在日本 TikTok 上热卖的厨房小工具，价格在1000日元以内</p>
        </div>
        <span>AI 选品助手</span>
      </div>
      <div className="prompt-box">
        <textarea
          placeholder="告诉我您想找什么样的产品？"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="prompt-bottom">
          <small>{message.length}/300</small>
          <select
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          >
            <option value={10}>10 条 · 10 积分</option>
            <option value={15}>15 条 · 15 积分</option>
            <option value={20}>20 条 · 20 积分</option>
          </select>
          <button
            className="primary"
            disabled={!message.trim() || busy}
            onClick={async () => {
              setBusy(true);
              try {
                await search(message, count);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "分析中..." : "智能选品"}
          </button>
        </div>
      </div>
    </section>
  );
}

function Dashboard() {
  const barRef = useRef<HTMLDivElement>(null);
  const radarRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<Record<string, unknown>>({});
  useEffect(() => {
    service
      .getPipelineStatus()
      .then((x) => setData(x || {}))
      .catch(() => setData({}));
  }, []);
  useEffect(() => {
    type Chart = {
      setOption: (option: unknown) => void;
      resize: () => void;
      dispose: () => void;
    };
    type Engine = { init: (el: HTMLElement) => Chart };
    const run = () => {
      const engine = (window as Window & { echarts?: Engine }).echarts;
      if (!engine || !barRef.current || !radarRef.current) return;
      const bar = engine.init(barRef.current);
      const radar = engine.init(radarRef.current);
      bar.setOption({
        tooltip: {
          trigger: "axis",
          backgroundColor: "rgba(20,22,28,.92)",
          borderColor: "rgba(214,69,43,.4)",
          textStyle: { color: "#ece9e2" },
        },
        grid: { left: 42, right: 18, top: 25, bottom: 28 },
        xAxis: {
          type: "category",
          data: ["市场数据", "AI衍生", "供应链匹配", "视频任务"],
          axisLine: { lineStyle: { color: "rgba(20,21,26,.15)" } },
          axisTick: { show: false },
          axisLabel: { color: "#6b6f78" },
        },
        yAxis: {
          type: "value",
          axisLabel: { color: "#8c9099" },
          splitLine: { lineStyle: { color: "rgba(20,21,26,.07)" } },
        },
        series: [
          {
            type: "bar",
            barWidth: 28,
            data: [
              Number(data.fastmoss_count || 12),
              Number(data.derived_count || 8),
              Number(data.match_count || 6),
              Number(data.video_count || 3),
            ],
            itemStyle: {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "#e0573f" },
                  { offset: 1, color: "#b8321f" },
                ],
              },
              borderRadius: [6, 6, 0, 0],
            },
          },
        ],
      });
      radar.setOption({
        tooltip: {
          backgroundColor: "rgba(20,22,28,.92)",
          borderColor: "rgba(214,69,43,.4)",
          textStyle: { color: "#ece9e2" },
        },
        radar: {
          indicator: [
            { name: "市场需求", max: 100 },
            { name: "短视频适配", max: 100 },
            { name: "利润空间", max: 100 },
            { name: "新奇特", max: 100 },
            { name: "复购属性", max: 100 },
            { name: "日本偏好", max: 100 },
          ],
          radius: "65%",
          axisName: { color: "#6b6f78" },
          splitLine: { lineStyle: { color: "rgba(20,21,26,.1)" } },
          splitArea: {
            areaStyle: { color: ["rgba(20,21,26,.02)", "rgba(20,21,26,.04)"] },
          },
          axisLine: { lineStyle: { color: "rgba(20,21,26,.12)" } },
        },
        series: [
          {
            type: "radar",
            data: [
              {
                value: [86, 91, 78, 88, 64, 84],
                name: "综合选品画像",
                areaStyle: { color: "rgba(214,69,43,.16)" },
                lineStyle: { color: "#d6452b", width: 2 },
                itemStyle: { color: "#c8a45c" },
              },
            ],
          },
        ],
      });
      const resize = () => {
        bar.resize();
        radar.resize();
      };
      window.addEventListener("resize", resize);
      return () => {
        window.removeEventListener("resize", resize);
        bar.dispose();
        radar.dispose();
      };
    };
    const existing = document.querySelector(
      'script[data-echarts="1"]',
    ) as HTMLScriptElement | null;
    if ((window as Window & { echarts?: Engine }).echarts) return run();
    if (existing) {
      existing.addEventListener("load", run);
      return () => existing.removeEventListener("load", run);
    }
    const script = document.createElement("script");
    script.dataset.echarts = "1";
    script.src =
      "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js";
    script.onload = run;
    document.head.appendChild(script);
    return () => {
      script.onload = null;
    };
  }, [data]);
  return (
    <section className="dashboard-page">
      <div className="dashboard-metrics">
        <div>
          <span>任务状态</span>
          <b>{String(data.status || "运行中")}</b>
        </div>
        <div>
          <span>今日任务</span>
          <b>{String(data.today_tasks || data.task_count || 0)}</b>
        </div>
        <div>
          <span>衍生品数量</span>
          <b>{String(data.derived_count || 0)}</b>
        </div>
        <div>
          <span>接口状态</span>
          <b className="ok">在线</b>
        </div>
      </div>
      <div className="dashboard-charts">
        <section className="chart-card">
          <h3>业务环节分布</h3>
          <div ref={barRef} className="echart-box" />
        </section>
        <section className="chart-card">
          <h3>选品雷达</h3>
          <div ref={radarRef} className="echart-box" />
        </section>
      </div>
    </section>
  );
}

function StorePage({
  user,
  notice,
  onCreditChange,
}: {
  user: User;
  notice: (s: string) => void;
  onCreditChange: (credits: number) => void;
}) {
  const [links, setLinks] = useState(() => {
    const value = localStorage.getItem("tk_publish_prefill_url") || "";
    localStorage.removeItem("tk_publish_prefill_url");
    return value;
  });
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
    const matches =
      links.match(
        /https?:\/\/detail\.1688\.com\/offer\/\d+\.html(?:\?[^\s|，,；;]*)?/gi,
      ) || [];
    const ids = links
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => /^\d{8,}$/.test(line))
      .map((id) => `https://detail.1688.com/offer/${id}.html`);
    return Array.from(new Set([...matches, ...ids]));
  }, [links]);
  const creditCost = offerUrls.length;
  const balance = Number(user.credits || 0);

  const refresh = async () => {
    try {
      const [a, b] = await Promise.all([
        service.getPublishLatest(),
        service.getPublishHistory(),
      ]);
      setLatest(a || null);
      setHistory(Array.isArray(b) ? b : []);
      if (a?.task_id && ["created", "running"].includes(String(a.status || "")))
        setTask(a);
    } catch (e) {
      notice(e instanceof Error ? e.message : "读取店铺任务失败");
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    if (!task?.task_id) return;
    const timer = window.setInterval(async () => {
      try {
        const current = await service.getPublishTask(String(task.task_id));
        setTask(current);
        setLatest(current);
        const status = String(current.status || "");
        if (
          [
            "imported",
            "import_failed",
            "image_failed",
            "failed",
            "batch_failed",
            "batch_partial_failed",
          ].includes(status)
        ) {
          window.clearInterval(timer);
          setBusy(false);
          await refresh();
        }
      } catch (e) {
        window.clearInterval(timer);
        setBusy(false);
        notice(e instanceof Error ? e.message : "读取上架进度失败");
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [task?.task_id]);

  async function loadShops() {
    setShopBusy(true);
    try {
      const result = await service.getMiaoshouShops({
        target_site: site,
        miaoshou_app_key: appKey,
        miaoshou_app_secret: appSecret,
        miaoshou_api_base_url: apiBase,
      });
      const options = Array.isArray(result?.shop_options)
        ? result.shop_options
        : [];
      setShops(options);
      if (options[0]?.shop_id) setShopId(String(options[0].shop_id));
      notice(`已读取 ${options.length} 个妙手店铺`);
    } catch (e) {
      notice(e instanceof Error ? e.message : "读取妙手店铺失败");
    } finally {
      setShopBusy(false);
    }
  }

  async function submit() {
    if (!offerUrls.length) {
      notice("请先填写货源链接，每行一个");
      return;
    }
    if (!shopId) {
      notice("请先刷新并选择妙手店铺");
      return;
    }
    if (creditCost > balance) {
      notice(`积分不足，本次需要 ${creditCost} 积分`);
      return;
    }
    setBusy(true);
    try {
      const result = await service.createPublishBatch({
        offer_urls: offerUrls,
        items: offerUrls.map((offer_url) => ({
          offer_url,
          package_weight_g: 500,
          package_length_cm: 10,
          package_width_cm: 10,
          package_height_cm: 40,
          profit_rule: profitRule,
          pricing_currency: "CNY",
        })),
        publish_count: offerUrls.length,
        target_channel: "TikTok Shop Japan",
        target_language: language,
        target_site: site,
        target_shop_id: Number(shopId),
        miaoshou_app_key: appKey,
        miaoshou_app_secret: appSecret,
        miaoshou_api_base_url: apiBase,
        enable_image_translation: imageTranslation,
        enable_image_removal: imageRemoval,
        enable_title_optimization: titleOptimization,
        enable_sku_optimization: skuOptimization,
        enable_description_optimization: descriptionOptimization,
        remove_logo: removeLogo,
        remove_transparent_text: removeTransparentText,
        remove_text: removeText,
        remove_psoriasis: removePsoriasis,
        profit_rule: profitRule,
        pricing_currency: "CNY",
        dry_run: dryRun,
      });
      if (typeof result.credit_balance === "number")
        onCreditChange(result.credit_balance);
      setTask(result);
      setLatest(result);
      await service.runPublishTask(String(result.task_id));
      notice(`已提交 ${offerUrls.length} 条上架任务`);
    } catch (e) {
      setBusy(false);
      notice(e instanceof Error ? e.message : "上架任务提交失败");
    }
  }
  const progress = (task?.progress || {}) as Record<string, unknown>;
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  const check = (
    label: string,
    value: boolean,
    setValue: (next: boolean) => void,
  ) => (
    <label className="store-check">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => setValue(e.target.checked)}
      />
      {label}
    </label>
  );
  return (
    <section className="store-page">
      <div className="store-heading">
        <div>
          <h2>店铺管理</h2>
          <p>配置店铺后，填写链接并开始执行。每上架一条商品消耗 1 积分。</p>
        </div>
        <div className="store-balance">
          当前积分 <b>{balance}</b>
        </div>
      </div>
      <div className="store-layout">
        <div className="store-main">
          <section className="store-card">
            <div className="store-card-heading">
              <div>
                <h3>妙手店铺配置</h3>
                <p>使用妙手开放平台 API 读取店铺并执行上架。</p>
              </div>
              <button onClick={loadShops} disabled={shopBusy}>
                {shopBusy ? "读取中..." : "刷新店铺"}
              </button>
            </div>
            <div className="store-form-grid">
              <label>
                目标地区
                <select
                  value={site}
                  onChange={(e) => {
                    setSite(e.target.value);
                    setShops([]);
                    setShopId("");
                  }}
                >
                  <option value="JP">日本</option>
                  <option value="US">美国</option>
                  <option value="GB">英国</option>
                </select>
              </label>
              <label>
                目标语言
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="ja">日语</option>
                  <option value="en">英语</option>
                </select>
              </label>
              <label className="store-span-2">
                目标店铺
                <select
                  value={shopId}
                  onChange={(e) => setShopId(e.target.value)}
                >
                  <option value="">请先刷新店铺</option>
                  {shops.map((shop) => (
                    <option
                      value={String(shop.shop_id)}
                      key={String(shop.shop_id)}
                    >
                      {String(shop.shop_name || `店铺 ${shop.shop_id}`)} ·{" "}
                      {String(shop.shop_id)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                AppKey
                <input
                  value={appKey}
                  onChange={(e) => setAppKey(e.target.value)}
                  placeholder="妙手 AppKey"
                />
              </label>
              <label>
                AppSecret
                <input
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  placeholder="妙手 AppSecret"
                />
              </label>
              <label className="store-span-2">
                API Base URL
                <input
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                />
              </label>
            </div>
          </section>
          <section className="store-card">
            <div className="store-card-heading">
              <div>
                <h3>1688 商品链接</h3>
                <p>每行一个链接，也支持直接填写 1688 商品 ID。</p>
              </div>
              <span className="store-count">已识别 {offerUrls.length} 条</span>
            </div>
            <textarea
              className="store-links"
              value={links}
              onChange={(e) => setLinks(e.target.value)}
              placeholder="https://detail.1688.com/offer/1234567890.html"
            />
          </section>
          <section className="store-card">
            <h3>上架处理选项</h3>
            <div className="store-option-group">
              <b>商品内容</b>
              <div className="store-checks">
                {check(
                  "妙手文案 / 标题优化",
                  titleOptimization,
                  setTitleOptimization,
                )}
                {check("规格优化", skuOptimization, setSkuOptimization)}
                {check(
                  "产品描述优化",
                  descriptionOptimization,
                  setDescriptionOptimization,
                )}
                {check("图片翻译", imageTranslation, setImageTranslation)}
                {check("图片智能抹除", imageRemoval, setImageRemoval)}
              </div>
            </div>
            <div className="store-option-group">
              <b>图片处理</b>
              <div className="store-checks">
                {check("去除 LOGO", removeLogo, setRemoveLogo)}
                {check(
                  "去除透明字块",
                  removeTransparentText,
                  setRemoveTransparentText,
                )}
                {check("去除文字", removeText, setRemoveText)}
                {check("去除牛皮癣", removePsoriasis, setRemovePsoriasis)}
              </div>
            </div>
            <div className="store-form-grid store-bottom-form">
              <label>
                目标利润
                <input
                  value={profitRule}
                  onChange={(e) => setProfitRule(e.target.value)}
                  placeholder="例如 20 或 20%"
                />
              </label>
              <label className="store-switch">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                />
                仅保存不发布
              </label>
            </div>
          </section>
          <section className="store-card store-submit">
            <div>
              <b>准备处理 {offerUrls.length} 条商品</b>
              <span>
                预计消耗 {creditCost} 积分 · 余额 {balance}
              </span>
            </div>
            <button
              className="primary"
              disabled={
                busy || !offerUrls.length || !shopId || creditCost > balance
              }
              onClick={submit}
            >
              {busy ? "任务处理中..." : "开始上架"}
            </button>
          </section>
        </div>
        <aside className="store-side">
          <section className="store-card store-progress">
            <div className="store-card-heading">
              <h3>任务进度</h3>
              <button onClick={refresh}>刷新</button>
            </div>
            {task ? (
              <>
                <div className="store-progress-line">
                  <b>{percent}%</b>
                  <span>
                    {String(
                      progress.message ||
                        task.message ||
                        task.status ||
                        "等待执行",
                    )}
                  </span>
                </div>
                <i>
                  <em style={{ width: `${percent}%` }} />
                </i>
                <p>任务 ID：{String(task.task_id || "-")}</p>
              </>
            ) : (
              <div className="store-empty">暂无进行中的任务</div>
            )}
          </section>
          <section className="store-card">
            <h3>最近任务</h3>
            <div className="store-history">
              {history.slice(0, 8).map((item, index) => (
                <div key={String(item.task_id || index)}>
                  <b>{String(item.workflow || "自动上架任务")}</b>
                  <span>
                    {String(item.status || "-")} ·{" "}
                    {String(item.created_at || "")}
                  </span>
                  <small>
                    {Array.isArray(item.offer_urls)
                      ? `${item.offer_urls.length} 条链接`
                      : String(item.offer_url || "")}
                  </small>
                </div>
              ))}
              {!history.length && (
                <div className="store-empty">暂无历史任务</div>
              )}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}

function VideoPage({
  user,
  notice,
  onCreditChange,
}: {
  user: User;
  notice: (s: string) => void;
  onCreditChange: (credits: number) => void;
}) {
  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [project, setProject] = useState<VideoProject | null>(null);
  const [step, setStep] = useState(0);
  const [titleValue, setTitleValue] = useState("");
  const [market, setMarket] = useState("日本");
  const [language, setLanguage] = useState("日语");
  const [details, setDetails] = useState("");
  const [strategy, setStrategy] = useState("auto_safe");
  const [script, setScript] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [role, setRole] = useState("产品主图");
  const [desc, setDesc] = useState("");
  const [model, setModel] = useState("auto");
  const [models, setModels] = useState<
    Array<{ label?: string; value?: string }>
  >([]);
  const [busy, setBusy] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const selectProject = (p: VideoProject) => {
    setProject(p);
    setTitleValue(p.title || "");
    setMarket(p.target_market || "日本");
    setLanguage(p.video_language || "日语");
    setDetails(p.product_details || "");
    setScript(p.script_text || "");
  };
  const refresh = async () => {
    try {
      const rows = await service.getVideoProjects();
      setProjects(rows);
      if (!project && rows[0]) selectProject(rows[0]);
    } catch (e) {
      notice(e instanceof Error ? e.message : "读取视频项目失败");
    }
  };
  useEffect(() => {
    refresh();
    service
      .getVideoModels()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);
  async function createProject() {
    setBusy(true);
    try {
      const p = await service.createVideoProject({
        title: titleValue || "新视频项目",
        target_market: market,
        video_language: language,
        product_details: details + "\nvideo_strategy_key:" + strategy,
      });
      setProjects((r) => [p, ...r]);
      selectProject(p);
      notice("视频项目已创建");
    } catch (e) {
      notice(e instanceof Error ? e.message : "创建项目失败");
    } finally {
      setBusy(false);
    }
  }
  async function saveInfo() {
    if (!project) {
      await createProject();
      return;
    }
    setBusy(true);
    try {
      const p = await service.updateVideoProject(project.id, {
        title: titleValue || "新视频项目",
        target_market: market,
        video_language: language,
        product_details: details + "\nvideo_strategy_key:" + strategy,
      });
      setProject(p);
      setProjects((r) => r.map((x) => (x.id === p.id ? p : x)));
      notice("产品信息已保存");
    } catch (e) {
      notice(e instanceof Error ? e.message : "保存产品信息失败");
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!project) {
      notice("请先保存项目");
      return;
    }
    if (!files.length) {
      notice("请选择产品图片");
      return;
    }
    setBusy(true);
    try {
      let p = project;
      for (let i = 0; i < files.length; i++)
        p = await service.uploadVideoAsset(project.id, files[i], {
          role,
          description: desc,
          is_primary: i === 0 ? 1 : 0,
        });
      setProject(p);
      setProjects((r) => r.map((x) => (x.id === p.id ? p : x)));
      setFiles([]);
      notice("产品图上传完成");
    } catch (e) {
      notice(e instanceof Error ? e.message : "上传图片失败");
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (!project) {
      notice("请先保存项目");
      return;
    }
    setBusy(true);
    try {
      const p = await service.generateVideoScript(project.id);
      setProject(p);
      setScript(p.script_text || "");
      setStep(2);
      notice("AI脚本已生成");
    } catch (e) {
      notice(e instanceof Error ? e.message : "脚本生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function saveScript() {
    if (!project) return;
    setBusy(true);
    try {
      const p = await service.saveVideoScript(project.id, {
        script_text: script,
        storyboard: [],
      });
      setProject(p);
      setProjects((r) => r.map((x) => (x.id === p.id ? p : x)));
      notice("脚本已保存");
    } catch (e) {
      notice(e instanceof Error ? e.message : "保存脚本失败");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (!project) {
      notice("请先保存项目");
      return;
    }
    if (Number(user.credits || 0) < 100) {
      notice("积分不足，提交生成视频需要100积分");
      return;
    }
    if (!project.assets?.length) {
      notice("请先上传产品图");
      return;
    }
    await saveScript();
    setTaskBusy(true);
    try {
      const p = await service.submitVideoTask(project.id, {
        generation_mode: "image_to_video",
        model_name: model,
      });
      if (typeof p.credit_balance === "number")
        onCreditChange(p.credit_balance);
      setProject(p);
      setProjects((r) => r.map((x) => (x.id === p.id ? p : x)));
      setStep(3);
      notice("视频任务已提交");
    } catch (e) {
      notice(e instanceof Error ? e.message : "提交视频失败");
    } finally {
      setTaskBusy(false);
    }
  }
  const task = project?.tasks?.[0];
  const video =
    task?.video_url || task?.result_video_url || project?.result_video_url;
  const url = (v?: string) =>
    v
      ? v.startsWith("http")
        ? v
        : String(service.api.defaults.baseURL || "") + v
      : "";
  const opts = models.length
    ? models
    : [
        { label: "默认推荐", value: "auto" },
        { label: "Seedance 2.0 Fast", value: "doubao-seedance-2-0-fast" },
        { label: "即梦电商特价", value: "buming:seedance-2-0-ecom-special" },
      ];
  const strategyLabels: Record<string, string> = {
    auto_safe: "自动稳妥",
    static_display: "静态展示",
    light_interaction: "轻交互",
    handheld_demo: "手持演示",
    wearable_demo: "佩戴演示",
  };
  const strategyLabel = strategyLabels[strategy] || strategy;
  return (
    <section className="video-page">
      <div className="video-heading">
        <div>
          <h2>视频生成</h2>
          <p>
            上传产品图，生成脚本，再提交视频。产品图会作为强参考。提交生成视频消耗
            100 积分。
          </p>
        </div>
        <div className="video-credit">
          当前积分 <b>{user.credits ?? 0}</b>
        </div>
      </div>
      <div className="video-layout">
        <aside className="video-projects">
          <div className="video-projects-head">
            <h3>我的项目</h3>
            <button onClick={refresh}>刷新</button>
          </div>
          <button className="video-new-project" onClick={createProject} disabled={busy}>
            + 新建项目
          </button>
          {projects.map((p) => {
            const st = p.status || "draft";
            const stClass =
              st === "generated" || st === "done" || st === "completed"
                ? "generated"
                : "configured";
            return (
              <button
                key={p.id}
                className={
                  project?.id === p.id ? "video-project active" : "video-project"
                }
                onClick={() => selectProject(p)}
              >
                <b>{p.title || "项目 " + p.id}</b>
                <div className="vp-meta">
                  <span className={"vp-status " + stClass}>{st}</span>
                </div>
              </button>
            );
          })}
          {!projects.length && <div className="video-empty">暂无项目，点上方新建</div>}
        </aside>
        <div className="video-workspace">
          <div className="video-context">
            <span className="vc-pill">
              <span className={"vc-dot " + (project ? "ok" : "")} />
              {project ? project.title || "未命名项目" : "尚未选择项目"}
            </span>
            <span className="vc-sep">·</span>
            <span>市场 <b>{project?.target_market || market}</b></span>
            <span className="vc-sep">·</span>
            <span>语言 <b>{project?.video_language || language}</b></span>
            <span className="vc-sep">·</span>
            <span>方案 <b>{strategyLabel}</b></span>
          </div>
          <div className="video-steps">
            {["产品信息", "产品图片", "视频脚本", "生成视频"].map((x, i) => (
              <button
                key={x}
                className={step === i ? "active" : i < step ? "done" : ""}
                onClick={() => setStep(i)}
              >
                <i>{step > i ? "✓" : i + 1}</i>
                <span className="vs-label">{x}</span>
              </button>
            ))}
          </div>
          {step === 0 && (
            <section className="video-card">
              <div className="video-card-head">
                <h3>第 1 步：填写产品信息</h3>
              </div>
              <div className="video-form">
                <label className="video-field video-field-full">
                  <span>项目标题</span>
                  <input
                    value={titleValue}
                    onChange={(e) => setTitleValue(e.target.value)}
                    placeholder="例如：开瓶器"
                  />
                </label>
                <div className="video-field-row">
                  <label className="video-field">
                    <span>目标市场</span>
                    <select
                      value={market}
                      onChange={(e) => setMarket(e.target.value)}
                    >
                      <option>日本</option>
                      <option>美国</option>
                      <option>英国</option>
                      <option>东南亚</option>
                    </select>
                  </label>
                  <label className="video-field">
                    <span>字幕语言</span>
                    <select
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                    >
                      <option>日语</option>
                      <option>英语</option>
                      <option>中文</option>
                      <option>韩语</option>
                    </select>
                  </label>
                  <label className="video-field">
                    <span>拍摄方案</span>
                    <select
                      value={strategy}
                      onChange={(e) => setStrategy(e.target.value)}
                    >
                      <option value="auto_safe">自动稳妥</option>
                      <option value="static_display">静态展示</option>
                      <option value="light_interaction">轻交互</option>
                      <option value="handheld_demo">手持演示</option>
                      <option value="wearable_demo">佩戴演示</option>
                    </select>
                  </label>
                </div>
                <label className="video-field video-field-full video-field-grow">
                  <span>产品详情</span>
                  <textarea
                    className="video-details"
                    value={details}
                    onChange={(e) => setDetails(e.target.value)}
                    placeholder="粘贴产品详情、卖点、人群、场景、风格要求。"
                    rows={10}
                  />
                </label>
                <div className="video-step-nav">
                  <div className="vs-left">
                    <button className="vs-back" onClick={saveInfo} disabled={busy || !project}>
                      保存当前信息
                    </button>
                    <button className="vs-back" onClick={createProject} disabled={busy}>
                      保存为新项目
                    </button>
                  </div>
                  <button className="vs-next" onClick={() => setStep(1)} disabled={!project}>
                    下一步：产品图片
                  </button>
                </div>
              </div>
            </section>
          )}
          {step === 1 && (
            <section className="video-card">
              <div className="video-card-head">
                <h3>第 2 步：上传产品图</h3>
              </div>
              <div className="video-upload-row">
                <input
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="图片角色"
                />
                <input
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  placeholder="图片说明"
                />
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(e) => setFiles(Array.from(e.target.files || []))}
                />
                <button
                  className="primary"
                  onClick={upload}
                  disabled={busy || !files.length || !project}
                >
                  上传图片
                </button>
              </div>
              <div className="video-assets">
                {(project?.assets || []).map((a) => (
                  <article key={a.id}>
                    <div className="video-asset-image">
                      {url(a.public_url || a.url) ? (
                        <img src={url(a.public_url || a.url)} />
                      ) : (
                        <span>暂无图片</span>
                      )}
                    </div>
                    <div className="video-asset-meta">
                      <b>{a.role || "产品图片"}</b>
                      <p>{a.description || "无说明"}</p>
                      <small>{a.is_primary ? "主参考图" : "参考图"}</small>
                    </div>
                    <button
                      className="video-asset-delete"
                      onClick={async () => {
                        if (project) {
                          try {
                            const p = await service.deleteVideoAsset(
                              project.id,
                              a.id,
                            );
                            setProject(p);
                            notice("图片已删除");
                          } catch (e) {
                            notice(e instanceof Error ? e.message : "删除失败");
                          }
                        }
                      }}
                    >
                      删除
                    </button>
                  </article>
                ))}
                {!project?.assets?.length && (
                  <div className="video-empty">暂无产品图</div>
                )}
              </div>
              <div className="video-step-nav">
                <button className="vs-back" onClick={() => setStep(0)}>
                  上一步
                </button>
                <button className="vs-next" onClick={() => setStep(2)} disabled={!project?.assets?.length}>
                  下一步：视频脚本
                </button>
              </div>
            </section>
          )}
          {step === 2 && (
            <section className="video-card">
              <div className="video-card-head">
                <h3>第 3 步：生成并修改脚本</h3>
                <div className="video-actions compact">
                  <button
                    className="primary"
                    onClick={generate}
                    disabled={busy || !project}
                  >
                    AI 生成脚本
                  </button>
                  <button onClick={saveScript} disabled={busy || !project}>
                    保存脚本
                  </button>
                </div>
              </div>
              <div className="video-script-wrap">
                <textarea
                  className="video-script"
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  placeholder="点击 AI 生成脚本，或直接输入脚本。"
                  rows={14}
                />
              </div>
              <div className="video-step-nav">
                <button className="vs-back" onClick={() => setStep(1)}>
                  上一步
                </button>
                <button className="vs-next" onClick={() => setStep(3)} disabled={!script?.trim()}>
                  下一步：生成视频
                </button>
              </div>
            </section>
          )}
          {step === 3 && (
            <section className="video-card video-generate-card">
              <div className="video-card-head">
                <h3>第 4 步：生成视频</h3>
              </div>
              <div className="video-generate-toolbar">
                <label>
                  生成方案
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  >
                    {opts.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label || o.value}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="spacer" />
                <button
                  className="primary"
                  onClick={submit}
                  disabled={taskBusy || !project}
                >
                  提交生成视频 · 100积分
                </button>
                <button
                  className="secondary"
                  onClick={async () => {
                    if (project && task?.id) {
                      try {
                        setProject(
                          await service.refreshVideoTask(project.id, task.id),
                        );
                        notice("任务已刷新");
                      } catch (e) {
                        notice(e instanceof Error ? e.message : "刷新失败");
                      }
                    }
                  }}
                >
                  刷新任务
                </button>
              </div>
              <div className="video-status-bar">
                <div>
                  <span>当前状态</span>
                  <b>{task?.status || project?.status || "未提交"}</b>
                  <small>
                    {task?.provider_task_id
                      ? "任务号：" + task.provider_task_id
                      : "尚未提交任务"}
                  </small>
                </div>
                {task?.error_message && (
                  <p className="video-error">{task.error_message}</p>
                )}
              </div>
              <div className="video-preview-wrap">
                {video ? (
                  <video className="video-preview" controls src={url(video)} />
                ) : (
                  <div className="video-preview-empty">
                    生成完成后会在这里预览视频
                  </div>
                )}
              </div>
              <div className="video-step-nav">
                <button className="vs-back" onClick={() => setStep(2)}>
                  上一步
                </button>
                <span className="vs-note">已是最后一步</span>
              </div>
            </section>
          )}
        </div>
      </div>
    </section>
  );
}

function WindowTitlebar() {
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
  return (
    <div className={`window-titlebar${isMac ? " mac" : ""}`}>
      <div className="window-brand">
        <span className="window-brand-mark">TK</span>
        <strong>益行跨境 AI 平台</strong>
      </div>
      <div className="window-tools">
        <button aria-label="Help" title="帮助">
          <Icon name="help" />
        </button>
        <button aria-label="Messages" title="消息">
          <Icon name="bell" />
        </button>
        <button aria-label="Settings" title="设置">
          <Icon name="settings" />
        </button>
        <div className="window-controls">
          <button
            aria-label="Minimize"
            title="最小化"
            onClick={() => window.desktop?.minimize?.()}
          >
            <Icon name="minimize" />
          </button>
          <button
            aria-label="Maximize"
            title="最大化"
            onClick={() => window.desktop?.toggleMaximize?.()}
          >
            <Icon name="maximize" />
          </button>
          <button
            className="close"
            aria-label="Close"
            title="关闭"
            onClick={() => window.desktop?.close?.()}
          >
            <Icon name="close" />
          </button>
        </div>
      </div>
    </div>
  );
} /*

export default function App2() { const stored = localStorage.getItem("tk_electron_user"); const [user, setUser] = useState<User | null>(() => stored ? JSON.parse(stored) : null); const [page, setPage] = useState<Page>("studio"); const [rows, setRows] = useState<Product[]>([]); const [selected, setSelected] = useState<Product | null>(null); const [notice, setNotice] = useState(""); const allowed = useMemo(() => menus.filter((m) => m.roles.includes(user?.role || "student")), [user]); const flash = (s: string) => { setNotice(s); window.setTimeout(() => setNotice(""), 3000); }; async function load(next: Page) { if (!["library", "rank", "favorites"].includes(next)) return; try { const data = next === "library" ? await service.getLibrary() : next === "favorites" ? await service.getFavorites() : await service.getRanks({ region: "JP", list_type: "new", page: 1, pagesize: 50, paged: true }); const list = Array.isArray(data) ? data : (data as { items?: Product[] })?.items || []; setRows(list); setSelected(list[0] || null); } catch (e) { flash(e instanceof Error ? e.message : "读取数据失败"); } } useEffect(() => { if (user) load(page); }, [user, page]); if (!user) return <><WindowTitlebar /><Login done={setUser} /></>; const collect = async (p: Product) => { try { await service.collect(p); flash("已加入采集箱"); } catch (e) { flash(e instanceof Error ? e.message : "加入失败"); } }; return <><WindowTitlebar /><div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">TK</div><div><b>益行跨境 AI 平台</b><span>TikTok 日本选品专家</span></div></div><nav>{allowed.map((m) => <button key={m.id} className={page === m.id ? "active" : ""} onClick={() => setPage(m.id)}><i>{m.icon}</i>{m.label}</button>)}</nav><div className="account"><div className="avatar">{(user.real_name || user.username || "系").slice(0, 1)}</div><div className="account-copy"><b>{user.real_name || user.username}</b><span>{user.role} · 积分 {user.credits ?? 0}</span></div><button className="logout" onClick={() => { service.logout(); setUser(null); }}>退出登录</button></div></aside><main className="main"><header><div><h1>{menus.find((m) => m.id === page)?.label}</h1><span>益行跨境 · 日本市场选品工作台</span></div></header>{page === "studio" && <Studio search={async (message, count) => { await service.searchSelection(message, count); flash("选品完成，结果已进入选品库"); setPage("library"); }} />}{["library", "rank", "favorites"].includes(page) && <Products page={page} rows={rows} selected={selected} onSelect={setSelected} onCollect={collect} />}{page === "dashboard" && <Dashboard />}{page === "store" && <Store notice={flash} />}{page === "video" && <Video notice={flash} />}{page === "profile" && <div className="module-card"><h2>个人中心</h2><p>当前账号：{user.username || user.real_name}</p><p>当前积分：{user.credits ?? 0}</p></div>}{page === "teacher" && <Teacher notice={flash} />}{page === "admin" && <Admin notice={flash} />}{notice && <div className="toast">{notice}</div>}</main></div>; }
*/

function Profile({
  user,
  onNotice,
  onCreditChange,
}: {
  user: User;
  onNotice: (message: string) => void;
  onCreditChange: (credits: number) => void;
}) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showQr, setShowQr] = useState(false);
  const [opacity, setOpacity] = useState(
    () =>
      JSON.parse(localStorage.getItem("tk_theme") || "{}").opacity || "0.30",
  );
  const credits = Number(user.credits ?? user.credit_balance ?? 0);
  function updateOpacity(value: string) {
    setOpacity(value);
    const saved = JSON.parse(localStorage.getItem("tk_theme") || "{}");
    const next = {
      font: "Microsoft YaHei UI",
      size: "14px",
      background: "background.png",
      ...saved,
      opacity: value,
    };
    localStorage.setItem("tk_theme", JSON.stringify(next));
    applyTheme(next);
  }
  return (
    <section className="profile">
      <div className="profile-card">
        <div className="avatar large-avatar">
          {(user.real_name || user.username || "A").slice(0, 1)}
        </div>
        <div>
          <h2>{user.real_name || user.username}</h2>
          <p>
            {user.role} · 当前积分 <b className="profile-credit">{credits}</b>
          </p>
        </div>
        <button
          className="secondary profile-refresh"
          onClick={async () => {
            try {
              const fresh = await service.getUser();
              onCreditChange(
                Number(fresh.credits ?? fresh.credit_balance ?? 0),
              );
              onNotice("积分余额已刷新");
            } catch (e) {
              onNotice(e instanceof Error ? e.message : "刷新积分失败");
            }
          }}
        >
          刷新余额
        </button>
      </div>
      <div className="settings-card credit-card">
        <h2>积分中心</h2>
        <div className="credit-balance">
          <strong>{credits}</strong>
          <span>当前可用积分</span>
        </div>
        <p>积分用于智能选品、衍生品生成、视频生成和自动上架等功能。</p>
        <button className="primary" onClick={() => setShowQr(true)}>
          扫码联系管理员充值
        </button>
      </div>
      <div className="settings-card">
        <h2>修改密码</h2>
        <label>
          原密码
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
        </label>
        <label>
          新密码
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </label>
        <button
          className="primary"
          onClick={async () => {
            try {
              await service.changePassword(oldPassword, newPassword);
              onNotice("密码已更新");
              setOldPassword("");
              setNewPassword("");
            } catch (e) {
              onNotice(e instanceof Error ? e.message : "修改失败");
            }
          }}
        >
          保存新密码
        </button>
      </div>
      <div className="settings-card transparency-settings">
        <h2>软件透明度</h2>
        <p>调整菜单栏和内容区的透明显现程度，修改会即时生效。</p>
        <label className="opacity-control">
          <span>透明度 {Math.round(Number(opacity) * 100)}%</span>
          <input
            type="range"
            min="0.12"
            max="0.72"
            step="0.02"
            value={opacity}
            onChange={(e) => updateOpacity(e.target.value)}
          />
        </label>
      </div>
      {showQr && (
        <div className="modal-backdrop" onClick={() => setShowQr(false)}>
          <div
            className="modal recharge-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setShowQr(false)}>
              ×
            </button>
            <h2>积分充值</h2>
            <p>扫码添加管理员好友，发送登录账号、充值金额和希望获得的积分。</p>
            <img src="/recharge_qr.png" alt="积分充值二维码" />
            <small>充值到账后，点击“刷新余额”即可查看。</small>
          </div>
        </div>
      )}
    </section>
  );
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
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${title(item).slice(0, 30) || "选品分析报告"}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

type PipelineReportItem = Record<string, unknown>;
type PipelineReportData = {
  id?: number;
  input_message?: string;
  status?: string;
  created_at?: string;
  finished_at?: string;
  counters?: Record<string, number>;
  board_groups?: Array<{ keyword?: string; items?: PipelineReportItem[] }>;
  board_items?: PipelineReportItem[];
  candidate_items?: PipelineReportItem[];
  final_items?: PipelineReportItem[];
  keywords?: Array<Record<string, unknown>>;
  ai_report?: Record<string, unknown>;
};

function htmlEscape(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pipelineItemValue(item: PipelineReportItem, ...keys: string[]) {
  for (const key of keys) {
    const value = item[key];
    if (value !== undefined && value !== null && String(value).trim())
      return value;
  }
  return "";
}

function pipelineReportRow(
  item: PipelineReportItem,
  index: number,
  status: string,
) {
  const name = pipelineItemValue(item, "title", "name") || "未命名商品";
  const image = pipelineItemValue(item, "image_url", "pic_url");
  const price = Number(pipelineItemValue(item, "price", "supplier_price") || 0);
  const sales = Number(
    pipelineItemValue(item, "sales_count", "supplier_sales_count") || 0,
  );
  const category = pipelineItemValue(item, "category") || "未分类";
  const source = pipelineItemValue(item, "source_url", "detail_url");
  return `<tr>
    <td class="index">${index + 1}</td>
    <td class="product-cell">${image ? `<img src="${htmlEscape(image)}" alt="" />` : '<span class="no-image">暂无图片</span>'}<b>${htmlEscape(name)}</b></td>
    <td>${htmlEscape(category)}</td>
    <td>${price ? `¥${price.toFixed(2)}` : "-"}</td>
    <td>${sales.toLocaleString("zh-CN")}</td>
    <td>${htmlEscape(status)}</td>
    <td>${source ? `<a href="${htmlEscape(source)}">查看</a>` : "-"}</td>
  </tr>`;
}

async function downloadPipelineReport(data: PipelineReportData) {
  const candidates = Array.isArray(data.candidate_items)
    ? data.candidate_items
    : [];
  const finals = Array.isArray(data.final_items) ? data.final_items : [];
  const boardFallback = (data.board_groups || []).flatMap((group) =>
    (group.items || []).filter((item) => !item.eliminated),
  );
  const candidateRows = candidates.length ? candidates : boardFallback;
  const finalRows = finals;
  const aiReport = data.ai_report || {};
  const marketIntro = (
    aiReport.market_intro && typeof aiReport.market_intro === "object"
      ? aiReport.market_intro
      : {}
  ) as Record<string, unknown>;
  const counters = data.counters || {};
  const keyword = data.input_message || "本次智能选品任务";
  const createdAt = new Date().toLocaleString("zh-CN");
  const table = (items: PipelineReportItem[], status: string) =>
    items.length
      ? `<table><thead><tr><th>#</th><th>商品</th><th>分类</th><th>价格</th><th>销量参考</th><th>结果</th><th>链接</th></tr></thead><tbody>${items.map((item, index) => pipelineReportRow(item, index, status)).join("")}</tbody></table>`
      : `<div class="empty">暂无${status}商品数据</div>`;
  const tracks = Array.isArray(aiReport.opportunity_tracks)
    ? (aiReport.opportunity_tracks as Array<Record<string, unknown>>)
    : [];
  const risks = Array.isArray(aiReport.risk_advice) ? aiReport.risk_advice : [];
  const reportHtml = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"/><title>智能选品报告</title><style>
    @page{size:A4;margin:15mm 13mm}*{box-sizing:border-box}body{margin:0;color:#1d2b3f;font-family:"Microsoft YaHei",Arial,sans-serif;font-size:12px;line-height:1.55;background:#fff}h1{margin:0 0 8px;font-size:25px;color:#132a47}h2{font-size:17px;margin:24px 0 9px;border-left:4px solid #159477;padding-left:9px;color:#183653}h3{font-size:14px;margin:14px 0 5px;color:#23614f}.cover{padding:28px 0 20px;border-bottom:2px solid #159477}.sub{color:#6d7c8d}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:16px 0}.metric{padding:10px;border:1px solid #dbe6e2;background:#f3faf7;border-radius:7px}.metric b{display:block;font-size:18px;color:#159477}.metric span{color:#667788}.intro{padding:12px 14px;background:#f7f9fb;border:1px solid #e1e7ed;border-radius:7px;white-space:pre-wrap}.note{color:#627487}.table-wrap{overflow:visible}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px}th{background:#e7f4ef;color:#245b4e;font-weight:700}th,td{border:1px solid #d7e1df;padding:6px 5px;vertical-align:middle;word-break:break-word}th:nth-child(1){width:4%}th:nth-child(2){width:38%}th:nth-child(3){width:15%}th:nth-child(4){width:10%}th:nth-child(5){width:11%}th:nth-child(6){width:10%}th:nth-child(7){width:12%}.product-cell{display:flex;align-items:center;gap:7px}.product-cell img{width:48px;height:48px;object-fit:contain;border:1px solid #edf0f2;border-radius:4px;background:#fff;flex:none}.product-cell b{font-weight:600}.no-image{width:48px;height:48px;display:inline-flex;align-items:center;justify-content:center;background:#f1f3f5;color:#8995a0;font-size:9px;flex:none}.index{text-align:center;color:#159477;font-weight:700}.empty{padding:25px;text-align:center;border:1px dashed #cddbd6;color:#7b8a95}.risk{padding:11px 14px;background:#fff8eb;border:1px solid #f0d59c;border-radius:7px}.footer{margin-top:25px;padding-top:8px;border-top:1px solid #d9e2e0;color:#89959c;font-size:10px}@media print{a{color:inherit;text-decoration:none}.page-break{page-break-before:always}}
  </style></head><body><main>
    <section class="cover"><h1>智能选品市场机会报告</h1><div class="sub">益行跨境 AI 平台 · 任务 #${htmlEscape(data.id || "-")} · 导出时间 ${createdAt}</div></section>
    <h2>一、选品任务概览</h2><div class="intro">${htmlEscape(keyword)}</div>
    <div class="summary"><div class="metric"><b>${counters.keywords || 0}</b><span>潜力方向</span></div><div class="metric"><b>${counters.supplier_candidates || 0}</b><span>供应链样本</span></div><div class="metric"><b>${counters.didadog_details || 0}</b><span>市场在售样本</span></div><div class="metric"><b>${finalRows.length || counters.final_products || 0}</b><span>精选商品</span></div></div>
    <p class="note">本报告仅保留任务结束时未淘汰的商品：候选蓝海商品与最终精选商品。灰色淘汰商品不进入本报告。</p>
    <h2>二、AI 市场分析</h2><p>${htmlEscape(aiReport.market_summary || "本次任务完成后由 general 大模型生成市场简介与选品判断。")}</p><div class="summary"><div class="metric"><b>市场规模</b><span>${htmlEscape(marketIntro.market_scale || "需进一步验证")}</span></div><div class="metric"><b>需求趋势</b><span>${htmlEscape(marketIntro.demand_trend || "需进一步验证")}</span></div><div class="metric"><b>竞争格局</b><span>${htmlEscape(marketIntro.competition_landscape || "需进一步验证")}</span></div></div>${tracks.map((track, index) => `<h3>${index + 1}. ${htmlEscape(track.track_name || "机会赛道")}</h3><p><b>机会：</b>${htmlEscape(track.opportunity || "-")}<br/><b>判断：</b>${htmlEscape(track.reason || "-")}</p>`).join("")}
    <h2>三、候选蓝海商品</h2><p class="note">经过价格筛选、市场样本拓展、销量聚合和蓝海过滤后保留的候选商品。</p><div class="table-wrap">${table(candidateRows, "候选品")}</div>
    <div class="page-break"></div><h2>四、最终精选商品</h2><p class="note">通过日本法规、禁运及限售规则后，综合流量、竞争、利润和供应链稳定性精选的商品。</p><div class="table-wrap">${table(finalRows, "精选品")}</div>
    <h2>五、AI 风险提示与行动建议</h2><div class="risk">${risks.length ? `<ul>${risks.map((risk) => `<li>${htmlEscape(risk)}</li>`).join("")}</ul>` : "上架前请再次核对日本法规、禁运禁售、平台限售、专利/商标及海关申报要求。限售商品需完成平台报白或取得对应资质后再运营。"}<p><b>候选品建议：</b>${htmlEscape(aiReport.candidate_strategy || "优先验证供应链稳定性、成本和短视频素材表现。")}<br/><b>精选品建议：</b>${htmlEscape(aiReport.final_strategy || "上架前完成法规、限售和专利风险复核。")}</p><p><b>结论：</b>${htmlEscape(aiReport.conclusion || "请结合商品清单进行人工复核。")}</p></div>
    <div class="footer">报告由益行跨境 AI 平台根据本次任务实时数据生成。打开后可使用打印功能选择“另存为 PDF”。</div>
  </main></body></html>`;
  if (window.desktop?.savePdf) {
    const result = await window.desktop.savePdf(
      reportHtml,
      `智能选品报告-${data.id || Date.now()}.pdf`,
    );
    if (!result.canceled && result.filePath)
      window.alert(`报告已保存到：${result.filePath}`);
    return;
  }
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(
    `${reportHtml}<script>window.onload=function(){setTimeout(function(){window.print()},500)};</script>`,
  );
  win.document.close();
}

function LibraryPage({
  rows,
  onPublish,
  onAddLibrary,
}: {
  rows: Product[];
  onPublish: (product: Product) => void;
  onAddLibrary: (product: Product) => Promise<void>;
}) {
  const [region, setRegion] = useState("ALL");
  const [category, setCategory] = useState("全部");
  const [regionExpand, setRegionExpand] = useState(false);
  const [categoryExpand, setCategoryExpand] = useState(false);
  const [selected, setSelected] = useState<Product | null>(null);
  const [regions, setRegions] = useState<
    Array<{ region_name?: string; region_code?: string }>
  >([]);
  const [report, setReport] = useState<PipelineReportData | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const categories = FIXED_CATEGORIES;
  const {
    derivedSource,
    setDerivedSource,
    derivedRows,
    derivedLoading,
    error,
    derivedReady,
    derivedAdded,
    setDerivedAdded,
    pipelineActive,
    pipelineProgress,
    pipelineStage,
    pipelineStatus,
    pipelineMessage,
    pipelineCounters,
    pipelineGroups,
    pipelineReportData,
    viewDerived,
    generateDerived,
    startDerived,
    closeDerived,
  } = useDerivation();
  const stats = useMemo(() => {
    const total = rows.length;
    const countries = new Set(
      rows.map((r) => String(r.region || "").toUpperCase()).filter(Boolean),
    ).size;
    const cats = new Set(
      rows.map((r) => String(r.category || "").trim()).filter(Boolean),
    ).size;
    const suppliable = rows.filter((r) => supplierUrl(r)).length;
    return { total, countries, cats, suppliable };
  }, [rows]);

  useEffect(() => {
    setSelected(rows[0] || null);
    service
      .getRegions()
      .then(setRegions)
      .catch(() => setRegions([]));
  }, [rows]);
  const filtered = useMemo(
    () =>
      rows.filter((item) => {
        const itemRegion = String(item.region || "").toUpperCase();
        const itemCategory = String(item.category || "");
        const regionMatch =
          region === "ALL" ||
          itemRegion === region ||
          (region === "SEA" &&
            ["ID", "VN", "TH", "MY", "PH", "SG"].includes(itemRegion));
        const categoryMatch =
          category === "全部" ||
          itemCategory.toLowerCase().includes(category.toLowerCase());
        return regionMatch && categoryMatch;
      }),
    [rows, region, category],
  );
  useEffect(() => {
    if (selected && !filtered.some((item) => pid(item) === pid(selected)))
      setSelected(filtered[0] || null);
  }, [filtered]);
  useEffect(() => {
    const tid = (selected as Record<string, unknown> | null)?.task_id;
    if (!tid) {
      setReport(null);
      return;
    }
    let cancelled = false;
    setReportLoading(true);
    service
      .getSelectionPipelineTask(Number(tid))
      .then((data) => {
        if (!cancelled) setReport(data as PipelineReportData);
      })
      .catch(() => {
        if (!cancelled) setReport(null);
      })
      .finally(() => {
        if (!cancelled) setReportLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);
  return (
    <>
      <section className="library-page">
        <div className="library-heading">
        <div>
          <h2>选品库</h2>
          <p>查看当前账号最近 7 天的 AI 搜索选品结果</p>
        </div>
      </div>
      <div className="library-stats">
        <div className="library-stat">
          <span className="stat-icon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/></svg>
          </span>
          <div className="stat-body">
            <div className="label">选品总数</div>
            <div className="value">{stats.total}</div>
            <div className="sub">当前账号已入库商品</div>
          </div>
        </div>
        <div className="library-stat">
          <span className="stat-icon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.8 2.8 2.8 15.2 0 18M12 3c-2.8 2.8-2.8 15.2 0 18"/></svg>
          </span>
          <div className="stat-body">
            <div className="label">覆盖国家</div>
            <div className="value">{stats.countries}</div>
            <div className="sub">跨境目标市场</div>
          </div>
        </div>
        <div className="library-stat">
          <span className="stat-icon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9-9-9z"/><circle cx="8" cy="8" r="1.6"/></svg>
          </span>
          <div className="stat-body">
            <div className="label">商品分类</div>
            <div className="value">{stats.cats}</div>
            <div className="sub">细分赛道数量</div>
          </div>
        </div>
        <div className="library-stat">
          <span className="stat-icon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="3.2"/><path d="M8 12l3 3 5-6"/></svg>
          </span>
          <div className="stat-body">
            <div className="label">可上品</div>
            <div className="value">{stats.suppliable}</div>
            <div className="sub">已匹配 1688 货源</div>
          </div>
        </div>
      </div>
      <div className="library-filters tiktok-filters">
        <RegionFilterRow
          value={region}
          onChange={setRegion}
          expanded={regionExpand}
          onToggleExpand={() => setRegionExpand((v) => !v)}
        />
        <CategoryFilterRow
          options={categories}
          value={category}
          onChange={setCategory}
          expanded={categoryExpand}
          onToggleExpand={() => setCategoryExpand((v) => !v)}
          allValue="全部"
        />
      </div>
      <div className="library-workspace">
        <section>
          <div className="smart-section-title">
            <h2>我的搜索选品</h2>
            <span>{filtered.length} 个商品</span>
          </div>
          <div className="library-grid">
            {filtered.map((item, index) => {
              const key = String(pid(item));
              const hasDerived =
                derivedReady[key] ?? Number(item.derived_count || 0) > 0;
              const rank = index + 1;
              const sales = Number(
                item.sales_count ?? item.supplier_sales_count ?? 0,
              );
              const maxSales = Math.max(
                1,
                ...filtered.map((r) =>
                  Number(r.sales_count ?? r.supplier_sales_count ?? 0),
                ),
              );
              const heat = Math.max(6, Math.round((sales / maxSales) * 100));
              return (
                <article
                  key={key}
                  className={
                    selected && pid(selected) === pid(item)
                      ? "library-card selected"
                      : "library-card"
                  }
                  onClick={() => setSelected(item)}
                >
                  <div className="library-card-image">
                    {picture(item) ? (
                      <img src={picture(item)} loading="lazy" />
                    ) : (
                      <div className="image-empty">暂无图片</div>
                    )}
                    <span
                      className={`card-index${
                        rank <= 3 ? ` top${rank === 1 ? "" : rank}` : ""
                      }`}
                    >
                      {rank}
                    </span>
                  </div>
                  <h3>{title(item)}</h3>
                  <div className="product-meta">
                    <strong>{money(item)}</strong>
                    <span>销量 {sales.toLocaleString()}</span>
                  </div>
                  <div className="library-card-heat">
                    <i><em style={{ width: `${heat}%` }} /></i>
                    <span>热度 {heat}%</span>
                  </div>
                  <div className="product-actions">
                    <button
                      className="primary"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (hasDerived) void viewDerived(item);
                        else void generateDerived(item);
                      }}
                    >
                      {hasDerived ? "查看衍生品" : "可以衍生"}
                    </button>
                    <button
                      className="secondary"
                      disabled={!supplierUrl(item)}
                      title={
                        supplierUrl(item)
                          ? ""
                          : "该商品暂无 1688 货源链接，无法加入上品"
                      }
                      onClick={(event) => {
                        event.stopPropagation();
                        onPublish(item);
                      }}
                    >
                      {supplierUrl(item) ? "加入上品" : "无货源链接"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
          {!filtered.length && (
            <div className="empty-state">
              暂无搜索选品，请先在智能选品对话框提交需求。
            </div>
          )}
        </section>
        <aside className="library-report">
          <div className="library-report-head">
            <h2>选品分析报告</h2>
            {report && (
              <button
                className="secondary small"
                onClick={() => downloadPipelineReport(report)}
              >
                ⇩ 导出报告
              </button>
            )}
          </div>
          {selected ? (
            reportLoading ? (
              <div className="empty-state">正在加载选品分析报告…</div>
            ) : report ? (
              <SelectionReportBody data={report} />
            ) : (
              <>
                <div className="smart-report-product">
                  {picture(selected) ? (
                    <img src={picture(selected)} />
                  ) : (
                    <div className="image-empty">暂无图片</div>
                  )}
                  <div>
                    <h3>{title(selected)}</h3>
                    <strong>{money(selected)}</strong>
                    <p>
                      销量{" "}
                      {Number(
                        selected.sales_count ??
                          selected.supplier_sales_count ??
                          0,
                      ).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="empty-state warn">
                  该商品暂无智能选品分析报告（仅展示基础信息）。
                </div>
                <div className="smart-report-actions">
                  <button
                    className="primary"
                    disabled={!supplierUrl(selected)}
                    title={
                      supplierUrl(selected)
                        ? ""
                        : "该商品暂无 1688 货源链接，无法加入上品"
                    }
                    onClick={() => onPublish(selected)}
                  >
                    加入上品
                  </button>
                </div>
              </>
            )
          ) : (
            <div className="empty-state">选择商品查看分析</div>
          )}
        </aside>
      </div>
    </section>
    {derivedSource && !pipelineActive && (
      <div className="modal-backdrop" onClick={() => setDerivedSource(null)}>
        <section
          className="modal derived-products-modal"
          onClick={(event) => event.stopPropagation()}
        >
          <button
            className="derived-modal-close"
            onClick={() => setDerivedSource(null)}
          >
            ×
          </button>
          <div className="derived-modal-head">
            {picture(derivedSource) ? (
              <img src={picture(derivedSource)} loading="lazy" />
            ) : (
              <div className="derived-modal-image image-empty" style={{ width: 52, height: 52, borderRadius: 10 }}>暂无图片</div>
            )}
            <div className="head-text">
              <span className="source-tag">原商品</span>
              <h2>查看衍生品</h2>
              <p className="source-title" title={title(derivedSource)}>
                {title(derivedSource)}
              </p>
            </div>
          </div>
          <div className="derived-modal-body">
            {derivedLoading ? (
              <div className="derived-empty">
                <span className="empty-icon">⟳</span>
                <b>正在读取衍生品</b>
                <span>请稍候，正在加载关联商品数据</span>
              </div>
            ) : error ? (
              <div className="derived-empty">
                <span className="empty-icon">!</span>
                <b>读取失败</b>
                <span>{error}</span>
              </div>
            ) : !derivedRows.length ? (
              <div className="derived-empty">
                <span className="empty-icon">✦</span>
                <b>暂无衍生品</b>
                <span>该商品尚未生成衍生方向，可点击「可以衍生」智能生成</span>
              </div>
            ) : (
              <div className="derived-modal-grid">
                {derivedRows.map((item, index) => {
                  const itemKey = String(pid(item));
                  const sales = Number(
                    item.sales_count ?? item.supplier_sales_count ?? 0,
                  );
                  const maxSales = Math.max(
                    1,
                    ...derivedRows.map((r) =>
                      Number(r.sales_count ?? r.supplier_sales_count ?? 0),
                    ),
                  );
                  const heat = Math.round((sales / maxSales) * 100);
                  return (
                    <article className="derived-modal-card" key={itemKey}>
                      <span className="derived-rank">{index + 1}</span>
                      <div className="derived-modal-image">
                        {picture(item) ? (
                          <img src={picture(item)} loading="lazy" />
                        ) : (
                          <div className="image-empty">暂无图片</div>
                        )}
                      </div>
                      <div className="derived-card-body">
                        <h3 title={title(item)}>{title(item)}</h3>
                        <div className="derived-meta">
                          <strong>{money(item)}</strong>
                          <span>销量 {sales.toLocaleString()}</span>
                        </div>
                        <div className="derived-heat">
                          <i><em style={{ width: `${heat}%` }} /></i>
                          <span>热度 {heat}%</span>
                        </div>
                        <button
                          className="derived-library-button"
                          disabled={derivedAdded[itemKey]}
                          onClick={async () => {
                            await onAddLibrary(item);
                            setDerivedAdded((current) => ({
                              ...current,
                              [itemKey]: true,
                            }));
                          }}
                        >
                          {derivedAdded[itemKey] ? "已加入选品库" : "加入选品库"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>
    )}
    {derivedSource && pipelineActive && (
      <DerivationPipelineModal
        source={derivedSource}
        progress={pipelineProgress}
        stage={pipelineStage}
        status={pipelineStatus}
        message={pipelineMessage}
        counters={pipelineCounters}
        groups={pipelineGroups}
        reportData={pipelineReportData}
        onStart={startDerived}
        onClose={closeDerived}
      />
    )}
  </>
);
}

function SmartSelectionLegacy({
  user,
  onNotice,
  onOpenLibrary,
  onCreditChange,
}: {
  user: User;
  onNotice: (message: string) => void;
  onOpenLibrary: () => void;
  onCreditChange: (credits: number) => void;
}) {
  const [message, setMessage] = useState("");
  const [count, setCount] = useState(10);
  const [items, setItems] = useState<Product[]>([]);
  const [boardCounters, setBoardCounters] = useState<Record<string, number>>(
    {},
  );
  const [selected, setSelected] = useState<Product | null>(null);
  const hotSearches = [
    "家居好物",
    "夏季防晒",
    "学生平价好物",
    "新奇特",
    "厨房小工具",
    "户外装备",
  ];
  const [taskId, setTaskId] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [taskMessage, setTaskMessage] = useState("");
  const [reportTab, setReportTab] = useState<"first" | "last">("first");
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [busy, setBusy] = useState(false);
  const [flowStatus, setFlowStatus] = useState<
    "idle" | "running" | "success" | "failed"
  >("idle");
  const [flowStep, setFlowStep] = useState(-1);
  const requiredCredits = count;
  const dimensions = [
    "使用场景",
    "商品周期性",
    "目标群体",
    "短视频流量种草适配能力",
    "日本市场偏好",
    "是否属于新奇特商品",
    "复购属性",
    "竞品属性",
  ];
  const flowNodes = [
    {
      title: "步骤 1：AI 对话挖掘潜力爆品",
      description:
        "输入需求对话，AI 精准拆解日本本土消费需求，自动产出多个适配日本 TikTok 短视频流量的潜力新品方向，清晰罗列完整商品名称。",
    },
    {
      title: "步骤 2：智能匹配优质供应链",
      description:
        "匹配优质产业带货源，评估供应稳定性、价格带与起订能力，筛选可快速响应的供货方案，锁定稳定可售供货。",
    },
    {
      title: "步骤 3：全网数据拓品，摸清市场全貌",
      description:
        "围绕核心款拓展日本市场在售样本，掌握同赛道关联商品的款式、热度与定价大盘。",
    },
    {
      title: "步骤 4：多维风控过滤，规避全部运营雷区",
      description:
        "依托益行深耕对日跨境的实战经验库，一次性筛除禁运禁售、专利侵权、平台限售、海关报关受限等高风险商品，从源头杜绝封号、扣货损失。",
    },
    {
      title: "步骤 5：热销竞品规避，抢占蓝海赛道",
      description:
        "自动比对平台现有爆款数据，直接剔除内卷严重的成熟热销品，帮你避开红海厮杀，优先锁定竞争小、增量空间足的蓝海单品。",
    },
    {
      title: "步骤 6：自动生成专业可视化选品报告",
      description:
        "一键输出完整决策报告，包含类目市场调研、精准产品定位画像、目标受众分析、全维度风险预警、平台限售标注，选品有据可依。",
    },
    {
      title: "步骤 7：输出最终精选 10 款优质爆品",
      description:
        "合规审核通过且非限售的商品中，按蓝海销量策略（销量升序）精选 10 款，输出可直接上架运营的清单。",
    },
  ];

  const flowStepFromStage = (stage: string, currentProgress: number) => {
    const stageIndex: Record<string, number> = {
      created: -1,
      keyword_generation: 0,
      supplier_search: 1,
      price_seed_selection: 1,
      image_search: 2,
      product_detail: 2,
      compliance_filter: 3,
      blue_ocean_filter: 4,
      report_generation: 5,
      final_selection: 6,
    };
    return stage in stageIndex
      ? stageIndex[stage]
      : Math.min(
          flowNodes.length - 1,
          Math.max(0, Math.floor(currentProgress / 15)),
        );
  };

  const refresh = async () => {
    try {
      const recommendations = await service.getRecommendations(12);
      const list = Array.isArray(recommendations) ? recommendations : [];
      setItems(
        list.map((item) => ({ ...item, region: "CN", currency: "CNY" })),
      );
      setSelected((current) =>
        current && list.some((item) => pid(item) === pid(current))
          ? current
          : list[0] || null,
      );
    } catch (e) {
      onNotice(e instanceof Error ? e.message : "读取今日推荐失败");
    }
    try {
      const saved = await service.getFavorites();
      setFavorites(Array.isArray(saved) ? saved : []);
    } catch {
      setFavorites([]);
    }
  };

  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    if (!taskId) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await service.getSelectionPipelineTask(taskId);
        setProgress(Math.max(0, Math.min(100, Number(status.progress || 0))));
        setTaskMessage(
          String(status.message || status.stage || "正在生成选品"),
        );
        setFlowStep(
          flowStepFromStage(
            String(status.stage || ""),
            Number(status.progress || 0),
          ),
        );
        setBoardCounters(status.counters || {});
        const boardItems = Array.isArray(status.board_items)
          ? status.board_items
          : [];
        if (boardItems.length) {
          setItems(
            boardItems.map((item: Record<string, unknown>) => ({
              ...item,
              title: item.title || "未命名商品",
              image_url: item.image_url || "",
              price: Number(item.price || 0),
              sales_count: Number(item.sales_count || 0),
              currency: item.currency || "CNY",
              region: item.region || "JP",
              source_type: item.source || "echotik",
            })) as Product[],
          );
        }
        if (status.status === "success") {
          window.clearInterval(timer);
          setTaskId(null);
          setBusy(false);
          setProgress(100);
          setFlowStep(flowNodes.length - 1);
          setFlowStatus("success");
          onNotice(`选品完成，共生成 ${status.success_count || count} 个商品`);
          onNotice("选品任务完成，任务看板已保留全部商品及淘汰状态");
        } else if (status.status === "failed") {
          window.clearInterval(timer);
          setTaskId(null);
          setBusy(false);
          setFlowStatus("failed");
          onNotice(String(status.message || "选品失败，积分已按系统结果处理"));
        }
      } catch (e) {
        window.clearInterval(timer);
        setTaskId(null);
        setBusy(false);
        onNotice(e instanceof Error ? e.message : "任务查询失败");
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [taskId, count]);

  async function submit() {
    if (!message.trim() || busy) return;
    if (Number(user.credits ?? 0) < requiredCredits) {
      onNotice(
        `积分不足，本次需要 ${requiredCredits} 积分，请前往个人中心充值`,
      );
      return;
    }
    setBusy(true);
    setProgress(5);
    setTaskMessage("正在提交 AI 选品任务");
    try {
      const result = await service.createSelectionPipelineTask(message.trim());
      if (!result.task_id) throw new Error("服务没有返回选品任务编号");
      setTaskId(Number(result.task_id));
      setItems([]);
      setBoardCounters({});
      setSelected(null);
      setFlowStatus("running");
      setFlowStep(0);
    } catch (e) {
      setBusy(false);
      setProgress(0);
      setFlowStep(-1);
      setFlowStatus("failed");
      onNotice(e instanceof Error ? e.message : "启动选品失败");
    }
  }

  function isFavorite(item: Product) {
    return favorites.some(
      (saved) =>
        title(saved) === title(item) && picture(saved) === picture(item),
    );
  }
  async function collect() {
    if (!selected) return;
    try {
      const saved = await service.collect(selected);
      setFavorites((list) => [saved?.data || selected, ...list]);
      onNotice("已加入采集箱");
    } catch (e) {
      onNotice(e instanceof Error ? e.message : "加入采集箱失败");
    }
  }
  const visibleDimensions =
    reportTab === "first" ? dimensions.slice(0, 6) : dimensions.slice(6);
  const flowClass = (index: number) =>
    index < flowStep
      ? "flow-node done"
      : index === flowStep
        ? `flow-node active ${flowStatus}`
        : "flow-node";
  return (
    <section className="smart-selection">
      <div className="smart-heading">
        <div>
          <h2>AI 智能选品</h2>
          <p>
            AI 全自动 TK 日区选品，七步严筛出 10
            款可上架爆品，省时避坑、利润可控！
          </p>
        </div>
        <button
          className="tutorial-button"
          onClick={() =>
            onNotice("描述商品、人群、预算或使用场景，点击智能选品提交任务。")
          }
        >
          ◉ 使用教程
        </button>
      </div>
      <div className="smart-workspace">
        <div className="smart-main">
          <div className="smart-chat">
            <div className="smart-chat-title">
              <span>✦</span>
              <b>告诉我您想找什么样的产品？</b>
              <small>AI 选品助手</small>
            </div>
            <textarea
              value={message}
              maxLength={300}
              placeholder="输入类目，挖掘 TK 日站蓝海爆品"
              onChange={(e) => setMessage(e.target.value)}
              disabled={busy}
            />
            <div className="smart-controls">
              <span>{message.length}/300</span>
              <select
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                disabled={busy}
              >
                <option value={10}>10 条 · 10 积分</option>
                <option value={15}>15 条 · 15 积分</option>
                <option value={20}>20 条 · 20 积分</option>
              </select>
              <button
                className="primary"
                disabled={!message.trim() || busy}
                onClick={submit}
              >
                智能选品
              </button>
            </div>
            <div className="smart-hot-searches">
              <b>热门搜索：</b>
              {hotSearches.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setMessage(item)}
                  disabled={busy}
                >
                  {item}
                </button>
              ))}
            </div>
            {busy && (
              <div className="smart-progress">
                <div>
                  <span>{taskMessage || "正在选品"}</span>
                  <b>{progress}%</b>
                </div>
                <i>
                  <em style={{ width: `${progress}%` }} />
                </i>
              </div>
            )}
          </div>
          <div className="selection-flow-panel">
            <div className="selection-flow-heading">
              <div>
                <h2>智能选品流程</h2>
                <p>
                  {flowStatus === "idle"
                    ? "点击智能选品后，实时查看每一步执行进度"
                    : flowStatus === "success"
                      ? "选品流程已完成，正在打开选品库"
                      : flowStatus === "failed"
                        ? "流程执行失败，请根据提示检查任务"
                        : `正在执行第 ${Math.min(flowNodes.length, flowStep + 1)} 步`}
                </p>
              </div>
              <span className={`flow-status ${flowStatus}`}>
                {flowStatus === "success"
                  ? "已完成"
                  : flowStatus === "failed"
                    ? "执行失败"
                    : flowStatus === "running"
                      ? "执行中"
                      : "待开始"}
              </span>
            </div>
            <div className="selection-flow-row">
              {flowNodes.slice(0, 2).map((node, index) => (
                <React.Fragment key={node.title}>
                  <div className={flowClass(index)}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <b>{node.title}</b>
                      <small>{node.description}</small>
                    </div>
                    <i>
                      {index < flowStep
                        ? "✓"
                        : index === flowStep && flowStatus === "running"
                          ? "●"
                          : ""}
                    </i>
                  </div>
                  {index < 1 && (
                    <em
                      className={
                        index < flowStep ? "flow-link done" : "flow-link"
                      }
                    >
                      →
                    </em>
                  )}
                </React.Fragment>
              ))}
            </div>
            <div className="selection-flow-row">
              {flowNodes.slice(2, 4).map((node, index) => {
                const actual = index + 2;
                return (
                  <React.Fragment key={node.title}>
                    <div className={flowClass(actual)}>
                      <span>{String(actual + 1).padStart(2, "0")}</span>
                      <div>
                        <b>{node.title}</b>
                        <small>{node.description}</small>
                      </div>
                      <i>
                        {actual < flowStep
                          ? "✓"
                          : actual === flowStep && flowStatus === "running"
                            ? "●"
                            : ""}
                      </i>
                    </div>
                    {index < 1 && (
                      <em
                        className={
                          actual < flowStep ? "flow-link done" : "flow-link"
                        }
                      >
                        →
                      </em>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
            <div className="selection-flow-row">
              {flowNodes.slice(4).map((node, index) => {
                const actual = index + 4;
                return (
                  <React.Fragment key={node.title}>
                    <div className={flowClass(actual)}>
                      <span>{String(actual + 1).padStart(2, "0")}</span>
                      <div>
                        <b>{node.title}</b>
                        <small>{node.description}</small>
                      </div>
                      <i>
                        {actual < flowStep
                          ? "✓"
                          : actual === flowStep && flowStatus === "running"
                            ? "●"
                            : ""}
                      </i>
                    </div>
                    {index < 2 && (
                      <em
                        className={
                          actual < flowStep ? "flow-link done" : "flow-link"
                        }
                      >
                        →
                      </em>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
          <div className="smart-section-title">
            <h2>今日选品推荐</h2>
            <span>AI 衍生品 · 日本站推荐</span>
          </div>
          <div className="smart-product-grid">
            {items.map((item) => (
              <article
                key={String(pid(item))}
                className={
                  selected && pid(selected) === pid(item)
                    ? "smart-product selected"
                    : "smart-product"
                }
                onClick={() => setSelected(item)}
              >
                <div className="smart-image">
                  {picture(item) ? (
                    <img src={picture(item)} loading="lazy" />
                  ) : (
                    <div className="image-empty">暂无图片</div>
                  )}
                </div>
                <h3>{title(item)}</h3>
                <div className="smart-product-bottom">
                  <strong>{money(item)}</strong>
                  <span>
                    销量{" "}
                    {Number(
                      item.sales_count ?? item.supplier_sales_count ?? 0,
                    ).toLocaleString()}
                  </span>
                </div>
              </article>
            ))}
          </div>
          {!items.length && (
            <div className="empty-state">
              今日暂无推荐商品，请先完成商品衍生或稍后再试。
            </div>
          )}
        </div>
        <aside className="smart-report">
          <h2>任务结果看板</h2>
          {selected ? (
            <>
              <div className="smart-report-product">
                {picture(selected) ? (
                  <img src={picture(selected)} />
                ) : (
                  <div className="image-empty">暂无图片</div>
                )}
                <div>
                  <h3>{title(selected)}</h3>
                  <strong>{money(selected)}</strong>
                  <p>
                    销量{" "}
                    {Number(
                      selected.sales_count ??
                        selected.supplier_sales_count ??
                        0,
                    ).toLocaleString()}
                  </p>
                  <p>
                    AI 参考分{" "}
                    {Number(
                      selected.ai_score ?? selected.weighted_score ?? 0,
                    ).toFixed(1)}
                  </p>
                </div>
              </div>
              <div className="smart-report-tabs">
                <button
                  className={reportTab === "first" ? "active" : ""}
                  onClick={() => setReportTab("first")}
                >
                  选品分析 1-6
                </button>
                <button
                  className={reportTab === "last" ? "active" : ""}
                  onClick={() => setReportTab("last")}
                >
                  选品分析 7-8
                </button>
              </div>
              <div className="smart-dimensions">
                {visibleDimensions.map((name, index) => (
                  <div key={name}>
                    <span className="smart-dimension-icon">{index + 1}</span>
                    <div>
                      <b>{name}</b>
                      <small>
                        {reportHas(selected, name)
                          ? "已生成分析报告"
                          : "暂无分析内容"}
                      </small>
                    </div>
                    <strong>{reportHas(selected, name) ? "参考" : "-"}</strong>
                  </div>
                ))}
              </div>
              <div className="smart-report-actions">
                <button className="secondary" onClick={collect}>
                  {isFavorite(selected) ? "★ 已在采集箱" : "☆ 加入采集箱"}
                </button>
                <button
                  className="primary"
                  onClick={() => downloadReport(selected)}
                >
                  ⇩ 导出报告
                </button>
              </div>
            </>
          ) : (
            <div className="empty-state">选择商品查看分析</div>
          )}
        </aside>
      </div>
    </section>
  );
}

const FLOW_NODES = [
  {
    title: "步骤 1｜AI 对话挖掘潜力爆品",
    description:
      "围绕你的选品需求，拆解日本本土消费场景与短视频流量特征，生成多个人群与使用场景下的潜力商品方向。",
  },
  {
    title: "步骤 2｜智能匹配优质供应链",
    description:
      "为每个潜力方向匹配优质产业带货源，评估供应稳定性、价格带与起订能力，锁定可执行货源基准。",
  },
  {
    title: "步骤 3｜全网数据拓品摸清市场",
    description:
      "围绕核心商品拓展日本市场在售样本，评估同款竞争热度与定价空间，为后续判断积累市场依据。",
  },
  {
    title: "步骤 4｜多维风控过滤",
    description:
      "多维审核剔除高风险商品：禁运禁售 · 专利商标侵权 · 海关报关受限 · 平台限售。",
  },
  {
    title: "步骤 5｜热销竞品规避 · 抢占蓝海",
    description:
      "比对平台爆款热度，规避内卷红海，锁定竞争小、增量足的潜力单品。",
  },
  {
    title: "步骤 6｜自动生成市场机会报告",
    description:
      "AI 生成选品报告：市场简介 · 产品定位画像 · 目标受众 · 机会赛道 · 风险预警 · 限售标注。",
  },
  {
    title: "步骤 7｜输出最终精选 10 款",
    description:
      "综合稳健、亮点、趋势等多维度精选 10 款可上架商品，覆盖不同风险收益偏好。",
  },
];
const HOT_SEARCHES = [
  "家居好物",
  "夏季防晒",
  "学生平价好物",
  "新奇特",
  "厨房小工具",
  "户外装备",
];
const STAGE_MAP: Record<string, number> = {
  created: -1,
  keyword_generation: 0,
  supplier_search: 1,
  price_seed_selection: 1,
  image_search: 2,
  product_detail: 2,
  compliance_filter: 3,
  blue_ocean_filter: 4,
  report_generation: 5,
  final_selection: 6,
};

function item1688Url(it: Record<string, unknown>): string {
  const candidates = [
    it.source_url,
    it.url,
    it.detail_url,
    it.product_url,
    it.product_url_1688,
    it.detail_url_1688,
  ];
  for (const u of candidates) {
    if (typeof u === "string" && /^https?:\/\//.test(u)) return u;
  }
  return "";
}

function _reportProductTexts(products: Array<Record<string, unknown>>) {
  return products
    .map((p) => String(p.title || p.product_title || p.name || ""))
    .filter(Boolean)
    .join(" ");
}

function _fallbackFrontendPositioning(text: string) {
  const t = text.toLowerCase();
  if (/化妆|护肤|美妆|口红|眼影|面膜|精华/.test(t))
    return {
      positioning: "面向日本年轻女性的日常美妆护肤小物，主打性价比与便携体验。",
      selling_point: "成分温和、包装精致、适合通勤或旅行随身携带。",
      style: "清新自然、韩系/日系少女感，强调无负担与快速上妆。",
    };
  if (/厨房|收纳|家居|清洁|餐具|置物|沥水/.test(t))
    return {
      positioning: "面向日本小户型家庭的实用型家居收纳与厨房 helper，解决空间局促痛点。",
      selling_point: "结构简单、易清洗、节省台面空间，提升日常家务效率。",
      style: "极简素色、MUJI 风，强调功能优先与耐用。",
    };
  if (/宠物|猫|狗|犬|喵|汪/.test(t))
    return {
      positioning: "面向日本宠物主人的日常消耗与陪伴用品，主打安全与趣味。",
      selling_point: "材质安全、互动性强，满足宠物玩耍与主人拍摄短视频需求。",
      style: "温馨可爱、ins 风，色彩柔和适合社交平台传播。",
    };
  if (/户外|运动|健身|瑜伽|跑步|露营/.test(t))
    return {
      positioning: "面向日本都市运动与户外爱好者，强调轻便、耐用与场景适配。",
      selling_point: "便携易收纳、功能明确，适合周末轻户外或居家健身。",
      style: "机能风、运动休闲，强调活力与实用。",
    };
  if (/数码|电子|配件|充电|线|耳机|手机壳/.test(t))
    return {
      positioning: "面向日本数码用户的实用配件，主打性价比与兼容性。",
      selling_point: "解决接口不匹配、收纳凌乱等日常小痛点，使用高频。",
      style: "科技极简、黑白灰为主，强调细节做工。",
    };
  if (/儿童|宝宝|婴儿|母婴|玩具|绘本/.test(t))
    return {
      positioning: "面向日本新手父母的母婴与儿童用品，主打安全与陪伴。",
      selling_point: "材质安全、设计圆润、便于家长清洁与收纳。",
      style: "柔和马卡龙色、卡通元素，传递安心与童趣。",
    };
  if (/服装|服饰|穿搭|T恤|裙子|外套/.test(t))
    return {
      positioning: "面向日本年轻消费者的潮流服饰单品，强调季节感与搭配性。",
      selling_point: "版型适配亚洲身材、面料舒适，适合日常通勤或周末出游。",
      style: "简约街头或日系通勤风，注重细节与百搭。",
    };
  return {
    positioning: "面向日本 TikTok 用户的日常消费小物，主打实用与性价比。",
    selling_point: "功能明确、价格亲民，适合短视频种草与冲动下单。",
    style: "简洁实用，包装与展示突出使用场景。",
  };
}

function _fallbackFrontendAudience(text: string) {
  const t = text.toLowerCase();
  if (/化妆|护肤|美妆|口红|眼影|面膜/.test(t))
    return {
      persona: "18-35 岁注重颜值与护肤的日本年轻女性，活跃于 TikTok 与 Instagram。",
      age_gender: "18-35 岁女性为主，学生与职场新人占比高。",
      pain_point: "预算有限但想尝试新品，担心成分刺激或妆效不持久。",
      scene: "晨起通勤、约会前补妆、旅行途中快速打理。",
    };
  if (/厨房|收纳|家居|清洁|餐具|置物/.test(t))
    return {
      persona: "25-45 岁日本家庭主妇与独居租房者，重视空间利用与清洁效率。",
      age_gender: "25-45 岁女性为主，独居青年与双职工家庭并重。",
      pain_point: "居住面积小、物品多，希望低价解决收纳与清洁难题。",
      scene: "日常厨房整理、浴室清洁、换季收纳。",
    };
  if (/宠物|猫|狗|犬/.test(t))
    return {
      persona: "25-45 岁日本宠物主，把宠物视为家庭成员，愿意为爱宠消费。",
      age_gender: "25-45 岁男女均有，女性略多。",
      pain_point: "市面宠物用品价格高、款式单一，想找有趣又安全的替代品。",
      scene: "居家陪伴、外出遛宠、宠物生日或节日社交分享。",
    };
  if (/户外|运动|健身|瑜伽|跑步|露营/.test(t))
    return {
      persona: "20-40 岁日本运动与户外爱好者，追求健康生活方式。",
      age_gender: "20-40 岁男女均衡，职场白领与学生群体为主。",
      pain_point: "专业装备贵、携带不便，希望找到轻便且高性价比的入门装备。",
      scene: "周末徒步、居家健身、公园跑步、轻露营。",
    };
  if (/数码|电子|配件|充电|线|耳机/.test(t))
    return {
      persona: "18-40 岁日本数码消费者，男性略多，关注兼容性与耐用度。",
      age_gender: "18-40 岁男性为主，女性用户随手机周边增长。",
      pain_point: "原装配件贵、线材易坏、接口不统一。",
      scene: "通勤途中、办公桌前、旅行出差、游戏娱乐。",
    };
  if (/儿童|宝宝|婴儿|母婴|玩具/.test(t))
    return {
      persona: "25-40 岁日本新手父母，重视安全、耐摔与易清洁。",
      age_gender: "25-40 岁父母为主，母亲决策占比高。",
      pain_point: "母婴店价格贵、款式同质化，希望找到安全且有趣的平价替代品。",
      scene: "居家陪伴、外出哄娃、亲友送礼、节日拍照。",
    };
  if (/服装|服饰|穿搭|T恤|裙子/.test(t))
    return {
      persona: "18-35 岁日本年轻消费者，关注季节穿搭与社交媒体潮流。",
      age_gender: "18-35 岁女性为主，男性潮牌用户为辅。",
      pain_point: "快时尚质量不稳定，想找价格合适又有设计感的单品。",
      scene: "日常通勤、周末出游、约会、社交媒体晒图。",
    };
  return {
    persona: "18-45 岁日本普通消费者，价格敏感且容易被短视频种草。",
    age_gender: "18-45 岁男女不限，年轻女性与家庭主妇为主力。",
    pain_point: "日常小物件购买渠道有限或价格偏高，希望找到实用平价替代品。",
    scene: "居家生活、通勤途中、周末休闲、节日送礼。",
  };
}

function _fallbackFrontendMarket(text: string) {
  const t = text.toLowerCase();
  if (/化妆|护肤|美妆|口红|眼影|面膜|精华/.test(t))
    return {
      market_scale: "日本美妆个护市场规模常年位居全球前列，年零售额超数万亿日元，TikTok 渠道仍处高速增长期，年轻女性为核心购买力。",
      demand_trend: "妆教与种草内容在 TikTok 持续走热，平价好物、国货成分党的需求快速放量，复购意愿强。",
      competition_landscape: "国际大牌与本土药妆品牌占据主流，但平价细分与差异化卖点仍有大量空白可被内容种草切入。",
    };
  if (/厨房|收纳|家居|清洁|餐具|置物|沥水/.test(t))
    return {
      market_scale: "日本住宅面积偏小，收纳清洁为刚需高频类目，市场规模稳定且体量庞大，线上渗透持续提升。",
      demand_trend: "MUJI 风、极简功能性产品接受度高，短视频展示使用场景的转化效果明显。",
      competition_landscape: "本土品牌成熟，但高性价比、强场景化的中国供应链商品仍有差异化空间。",
    };
  if (/宠物|猫|狗|犬|喵|汪/.test(t))
    return {
      market_scale: "日本宠物经济成熟且持续增长，宠物主将宠物视为家人，用品、零食、互动玩具复购率高。",
      demand_trend: "宠物陪伴与社交分享内容在 TikTok 受欢迎，有趣又安全的替代品需求旺盛。",
      competition_landscape: "本土宠物品牌较多，但趣味化、平价化供给仍不充分，出海空间明显。",
    };
  if (/户外|运动|健身|瑜伽|跑步|露营/.test(t))
    return {
      market_scale: "疫情后健康生活与轻户外需求上升，便携装备市场稳步扩大，入门级消费占比提升。",
      demand_trend: "周末徒步、居家健身内容在社媒增长，轻便高性价比入门装备种草转化明显。",
      competition_landscape: "专业品牌价格偏高，平价入门替代品尚不充分，内容驱动转化效率高。",
    };
  if (/数码|电子|配件|充电|线|耳机|手机壳/.test(t))
    return {
      market_scale: "日本 3C 配件市场庞大且稳定，手机周边与充电类目高频复购，女性用户随手机壳增长。",
      demand_trend: "兼容性、耐用性与颜值并重的实用配件需求稳定，短视频开箱测评转化好。",
      competition_landscape: "原装与本土品牌占主流，但高性价比第三方配件仍有充足空间。",
    };
  if (/儿童|宝宝|婴儿|母婴|玩具|绘本/.test(t))
    return {
      market_scale: "日本少子化下母婴消费更重品质安全，客单高、复购稳，新手父母愿为安全有趣产品付费。",
      demand_trend: "安全、耐摔、易清洁的育儿用品需求刚性，社媒母婴博主种草影响力强。",
      competition_landscape: "本土母婴品牌强势，但平价安全替代品仍有切入机会。",
    };
  if (/服装|服饰|穿搭|T恤|裙子|外套/.test(t))
    return {
      market_scale: "日本时尚消费成熟，季节穿搭与社媒潮流驱动，平价有设计感单品市场空间充足。",
      demand_trend: "日常通勤与周末出游穿搭内容热度高，百搭基础款与潮牌平替需求稳定。",
      competition_landscape: "快时尚同质化严重，有设计感且价格合适的差异化单品仍有空白。",
    };
  return {
    market_scale: "日本 TikTok 电商处于高速增长期，内容种草转化效率高于传统货架，日用消费小物市场广阔。",
    demand_trend: "短视频种草驱动冲动消费，平价实用小物的需求持续放量。",
    competition_landscape: "头部品类竞争激烈，但大量细分蓝海仍待内容切入。",
  };
}

function parseAiReport(
  report: Record<string, unknown> | undefined | null,
  products: Array<Record<string, unknown>> = [],
) {
  const safe = (report || {}) as Record<string, unknown>;
  const intro = (safe.market_intro || {}) as Record<string, unknown>;
  const tracks = Array.isArray(safe.opportunity_tracks)
    ? safe.opportunity_tracks
    : [];
  const risks = Array.isArray(safe.risk_advice) ? safe.risk_advice : [];
  const placeholderSet = new Set(["需进一步验证", "待定", "暂无", "未知", "unknown", "n/a", ""]);
  const evasiveHints = [
    "需进一步验证", "暂未获取", "暂未", "缺乏公开", "缺乏权威", "缺乏可", "待补充",
    "待确认", "数据缺失", "暂无精准", "未获取到", "时序增长数据", "有待核验",
    "无法获取", "缺少权威", "暂无权威", "未获取到明确", "缺乏明确", "尚不明朗",
    "暂无可靠", "未能获取", "暂无公开的", "暂无对外", "暂无第三方",
  ];
  const isEvasive = (s: string) => evasiveHints.some((h) => s.toLowerCase().includes(h));
  const combinedText = _reportProductTexts(products);
  const fallbackPos = _fallbackFrontendPositioning(combinedText);
  const fallbackAud = _fallbackFrontendAudience(combinedText);
  const fallbackMkt = _fallbackFrontendMarket(combinedText);

  const rawPP =
    safe.product_positioning && typeof safe.product_positioning === "object"
      ? (safe.product_positioning as Record<string, unknown>)
      : {};
  const productPositioning = {
    positioning: placeholderSet.has(String(rawPP.positioning || "").trim())
      ? fallbackPos.positioning
      : String(rawPP.positioning || ""),
    selling_point: placeholderSet.has(String(rawPP.selling_point || "").trim())
      ? fallbackPos.selling_point
      : String(rawPP.selling_point || ""),
    style: placeholderSet.has(String(rawPP.style || "").trim())
      ? fallbackPos.style
      : String(rawPP.style || ""),
  };

  const rawTA =
    safe.target_audience && typeof safe.target_audience === "object"
      ? (safe.target_audience as Record<string, unknown>)
      : {};
  const rawPersona = placeholderSet.has(String(rawTA.persona || "").trim())
    ? fallbackAud.persona
    : String(rawTA.persona || "");
  const rawAgeGender = placeholderSet.has(String(rawTA.age_gender || "").trim())
    ? fallbackAud.age_gender
    : String(rawTA.age_gender || "");
  // 用户要求：年龄性别包含在人群画像内，不单独展示
  const personaCombined =
    rawPersona.includes(rawAgeGender) || !rawAgeGender
      ? rawPersona
      : `${rawPersona} 主要受众为${rawAgeGender}`;
  const targetAudience = {
    persona: personaCombined,
    age_gender: "", // 保留字段但不再独立展示
    pain_point: placeholderSet.has(String(rawTA.pain_point || "").trim())
      ? fallbackAud.pain_point
      : String(rawTA.pain_point || ""),
    scene: placeholderSet.has(String(rawTA.scene || "").trim())
      ? fallbackAud.scene
      : String(rawTA.scene || ""),
  };

  return {
    marketScale:
      placeholderSet.has(String(intro.market_scale || "").trim()) ||
      isEvasive(String(intro.market_scale || ""))
        ? fallbackMkt.market_scale
        : String(intro.market_scale || ""),
    demandTrend:
      placeholderSet.has(String(intro.demand_trend || "").trim()) ||
      isEvasive(String(intro.demand_trend || ""))
        ? fallbackMkt.demand_trend
        : String(intro.demand_trend || ""),
    competition:
      placeholderSet.has(String(intro.competition_landscape || "").trim()) ||
      isEvasive(String(intro.competition_landscape || ""))
        ? fallbackMkt.competition_landscape
        : String(intro.competition_landscape || ""),
    tracks: (tracks as any[]).map((t) => ({
      name: String(t?.track_name || t?.name || "未命名赛道"),
      opportunity: String(t?.opportunity || ""),
      reason: String(t?.reason || ""),
    })),
    candidateStrategy: String(safe.candidate_strategy || ""),
    finalStrategy: String(safe.final_strategy || ""),
    risks,
    productPositioning,
    targetAudience,
    restrictionFlags: Array.isArray(safe.restriction_flags)
      ? (safe.restriction_flags as unknown[])
      : [],
    conclusion: String(safe.conclusion || ""),
  };
}

const TIER_LABEL: Record<string, string> = {
  hot: "爆款",
  regular: "常规",
  new: "新品",
  quirky: "奇特",
  highlight: "亮点",
};

function SelectionReportBody({
  data,
}: {
  data: PipelineReportData;
}) {
  const finals = data.final_items || [];
  const candidates = data.candidate_items || [];
  const report = parseAiReport(data.ai_report, [...finals, ...candidates]);
  const allProducts = finals.length ? finals : candidates;
  const tracks = report.tracks.length
    ? report.tracks
    : [{ name: "核心机会赛道", opportunity: "基于本次筛选结果", reason: "" }];
  const perTrack = 2;

  const tierCounts: Record<string, number> = finals.reduce<Record<string, number>>((acc, it) => {
    const t = String((it as Record<string, unknown>)["tier"] || "regular");
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});

  return (
    <>
          <div className="report-cover">
            <span className="report-badge">已生成</span>
            <h3>智能选品市场机会报告</h3>
            <p>
              任务 #{data.id}
              {data.created_at
                ? " · " + new Date(String(data.created_at)).toLocaleDateString("zh-CN")
                : ""}
            </p>
            <div className="report-tags">
              <span>日本 TikTok</span>
              <span>蓝海选品</span>
              <span>供应链优选</span>
            </div>
          </div>

          <div className="report-section">
            <h4>一、市场简介</h4>
            <div className="report-intro-grid">
              <div>
                <b>市场规模</b>
                <p>{report.marketScale || "需进一步验证"}</p>
              </div>
              <div>
                <b>需求趋势</b>
                <p>{report.demandTrend || "需进一步验证"}</p>
              </div>
              <div>
                <b>竞争格局</b>
                <p>{report.competition || "需进一步验证"}</p>
              </div>
            </div>
          </div>

          <div className="report-section">
            <h4>二、产品定位画像</h4>
            <div className="report-intro-grid">
              <div><b>定位描述</b><p>{String(report.productPositioning.positioning || "需进一步验证")}</p></div>
              <div><b>核心卖点</b><p>{String(report.productPositioning.selling_point || "需进一步验证")}</p></div>
              <div><b>风格调性</b><p>{String(report.productPositioning.style || "需进一步验证")}</p></div>
            </div>
          </div>

          <div className="report-section">
            <h4>三、目标受众分析</h4>
            <div className="report-intro-grid">
              <div><b>人群画像</b><p>{String(report.targetAudience.persona || "需进一步验证")}</p></div>
              <div><b>痛点需求</b><p>{String(report.targetAudience.pain_point || "需进一步验证")}</p></div>
              <div><b>使用场景</b><p>{String(report.targetAudience.scene || "需进一步验证")}</p></div>
            </div>
          </div>

          {tracks.map((track, idx) => {
            const trackItems = allProducts.slice(
              idx * perTrack,
              idx * perTrack + perTrack,
            );
            return (
              <div className="report-section" key={idx}>
                <h4>
                  机会赛道{idx === 0 ? "一" : idx === 1 ? "二" : "三"}：{track.name}
                </h4>
                {track.opportunity ? (
                  <p className="report-track-desc">{track.opportunity}</p>
                ) : null}
                {track.reason ? (
                  <p className="report-track-reason">{track.reason}</p>
                ) : null}
                <div className="report-products">
                  {trackItems.map((it, i) => {
                    const key = String(it.id || it.title || i);
                    const url = item1688Url(it);
                    return (
                      <a
                        className="report-product-card"
                        key={key}
                        href={url || undefined}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <div className="report-product-img">
                          {it.image_url ? (
                            <img src={String(it.image_url)} alt="" />
                          ) : (
                            <span>无图</span>
                          )}
                        </div>
                        <div className="report-product-info">
                          <b>{String(it.title || "未命名商品")}</b>
                          <div className="report-product-price-row">
                            <span className="report-product-market">
                              US${Number(it.price || 0).toFixed(2)}
                            </span>
                            <span className="report-product-source">
                              ¥
                              {Number(
                                it.source_price || it.price || 0,
                              ).toFixed(2)}
                            </span>
                          </div>
                          <span className="report-product-shop">
                            {String(it.shop_name || "优选供应商")}
                          </span>
                          <span className="report-product-link">
                            查看货源 →
                          </span>
                        </div>
                        <span className="report-library-badge">已自动加入选品库</span>
                      </a>
                    );
                  })}
                </div>
              </div>
            );
          })}

          <div className="report-section">
            <h4>四、精选组合概览</h4>
            <p className="report-strategy">
              本次最终 10 款覆盖 <b>爆款 / 常规 / 新品 / 奇特 / 亮点</b> 五类，兼顾已验证需求与内容出圈潜力：
            </p>
            <div className="report-portfolio">
              {["hot", "regular", "new", "quirky", "highlight"].map((t) => (
                <span className={`report-portfolio-chip ${t}`} key={t}>
                  {TIER_LABEL[t] || t} ×{tierCounts[t] || 0}
                </span>
              ))}
            </div>
            <p className="report-strategy">
              <b>爆款</b>需求确定、<b>常规</b>低风险稳健、<b>新品</b>踩中趋势上升期、<b>奇特</b>视觉吸睛有话题、<b>亮点</b>差异化且适合短视频出圈——多元组合降低单一品类风险。
            </p>
          </div>

          <div className="report-section">
            <h4>五、平台限售标注</h4>
            {report.restrictionFlags.length > 0 ? (
              <ul className="report-risk-list">
                {report.restrictionFlags.map((r, i) => (
                  <li key={i}>
                    {typeof r === "string"
                      ? r
                      : String(
                          (r as Record<string, unknown>)?.desc ||
                            (r as Record<string, unknown>)?.category ||
                            JSON.stringify(r),
                        )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="report-strategy">
                本次精选/候选商品未命中日本限售规则，无需额外报白即可运营。
              </p>
            )}
          </div>

          <div className="report-section">
            <h4>六、风险提示与行动建议</h4>
            {report.risks.length > 0 ? (
              <ul className="report-risk-list">
                {report.risks.map((r, i) => (
                  <li key={i}>{String(r)}</li>
                ))}
              </ul>
            ) : null}
            {report.candidateStrategy ? (
              <p className="report-strategy">
                <b>候选策略：</b>
                {report.candidateStrategy}
              </p>
            ) : null}
            {report.finalStrategy ? (
              <p className="report-strategy">
                <b>精选策略：</b>
                {report.finalStrategy}
              </p>
            ) : null}
            {report.conclusion ? (
              <p className="report-conclusion">{report.conclusion}</p>
            ) : null}
          </div>
        </>
  );
}

function SelectionReport({
  data,
  onClose,
}: {
  data: PipelineReportData;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="report-modal">
      <div className="report-modal-backdrop" onClick={onClose} />
      <div className="report-modal-content">
        <div className="report-modal-header">
          <h2>智能选品市场机会报告</h2>
          <button className="report-modal-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <div className="report-modal-body">
          <SelectionReportBody data={data} />
        </div>
      </div>
    </div>
  );
}

function Reel({ items, tick }: { items: Array<Record<string, unknown>>; tick: number }) {
  if (!items.length) return <div className="sel-reel-empty">无货源</div>;
  const n = items.length;
  const active = ((tick % n) + n) % n;
  const prev = (active - 1 + n) % n;
  const next = (active + 1) % n;
  const ai = items[active];
  const pi = items[prev];
  const ni = items[next];
  return (
    <div className="sel-reel">
      <div className="sel-reel-peek">
        {pi?.image_url ? <img src={String(pi.image_url)} alt="" /> : <span />}
      </div>
      <div className="sel-reel-window">
        {ai?.image_url ? (
          <img key={active} className="sel-reel-img" src={String(ai.image_url)} alt="" />
        ) : (
          <span>{active + 1}</span>
        )}
      </div>
      <div className="sel-reel-peek">
        {ni?.image_url ? <img src={String(ni.image_url)} alt="" /> : <span />}
      </div>
      <div className="sel-reel-dots">
        {items.slice(0, 8).map((_, i) => (
          <i key={i} className={i === active ? "on" : ""} />
        ))}
      </div>
    </div>
  );
}

function SelectionStage(props: {
  status: string;
  currentStep: number;
  keywords: Array<Record<string, unknown>>;
  groups: Array<{ keyword_id: number; keyword: string; items: Array<Record<string, unknown>> }>;
  counters: Record<string, number>;
  boardItems: Array<Record<string, unknown>>;
  finalItems: Array<Record<string, unknown>>;
}) {
  const { status, currentStep, keywords, groups, counters, boardItems, finalItems } = props;
  const [reelTick, setReelTick] = useState(0);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [showAllKeywords, setShowAllKeywords] = useState(false);
  useEffect(() => {
    const prefersReduce =
      typeof window !== "undefined" &&
      !!window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduce) return;
    const t = window.setInterval(() => setReelTick((v) => v + 1), 2200);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (keywords.length === 0) setShowAllKeywords(false);
  }, [keywords.length]);

  const allDone = status === "success";
  const liveGroups = useMemo(
    () => groups.filter((g) => g.keyword_id !== -1 && g.keyword_id !== -2),
    [groups],
  );
  const eliminated = useMemo(() => {
    let e = 0, k = 0;
    for (const g of liveGroups)
      for (const it of g.items) {
        if (it.eliminated) e++;
        else k++;
      }
    return { e, k };
  }, [liveGroups]);
  const echotik = useMemo(
    () => boardItems.filter((b) => b.source === "echotik" || b.source === "supply_fallback").slice(0, 8),
    [boardItems],
  );
  const hasSupplyFallback = useMemo(
    () => boardItems.some((b) => b.source === "supply_fallback"),
    [boardItems],
  );
  const steps = [
    { key: "keyword", title: "AI 对话挖掘潜力爆品", icon: "🔍" },
    { key: "supplier", title: "智能匹配优质供应链", icon: "🔗" },
    { key: "trend", title: "全网数据拓品摸清市场", icon: "🌐" },
    { key: "risk", title: "多维风控过滤", icon: "🛡" },
    { key: "blue", title: "热销竞品规避 · 抢占蓝海", icon: "🌊" },
    { key: "report", title: "自动生成市场机会报告", icon: "📊" },
    { key: "final", title: "输出最终精选 10 款", icon: "🏆" },
  ];

  if (status === "idle") {
    return (
      <div className="empty-state">
        任务开始后，右侧将逐步呈现 AI 挖掘潜力方向、供应链匹配、风控审核与最终精选报告。
      </div>
    );
  }

  function summaryFor(idx: number): string {
    switch (idx) {
      case 0:
        return keywords.length ? "需求解析完成" : "正在挖掘消费场景";
      case 1:
        return counters.supplier_candidates ? "货源匹配完成" : "正在匹配供应链";
      case 2:
        return counters.image_search_entries ? "市场样本拓展完成" : "正在拓展市场样本";
      case 3:
        return eliminated.e !== undefined ? "风控审核完成" : "正在多维风控审核";
      case 4:
        return counters.candidates ? "蓝海机会识别完成" : "正在识别蓝海机会";
      case 5:
        return allDone ? "报告已生成" : "报告生成中";
      case 6:
        return finalItems.length ? "精选商品已出炉" : "正在精选最终商品";
      default:
        return "";
    }
  }

  function linesFor(key: string): Array<{ kind: string; text: string }> {
    switch (key) {
      case "keyword":
        return [
          { kind: "think", text: "解析选品需求，拆解日本本土消费场景与短视频流量特征" },
          { kind: "think", text: "围绕需求生成潜力商品方向，覆盖多个人群与使用场景" },
          { kind: "metric", text: keywords.length ? "潜力方向已生成" : "正在生成潜力方向…" },
        ];
      case "supplier":
        return [
          { kind: "think", text: "定向匹配优质产业带货源" },
          { kind: "think", text: "评估供应稳定性、价格带与起订能力" },
          { kind: "metric", text: counters.supplier_candidates ? "货源基准已锁定" : "正在锁定货源基准…" },
        ];
      case "trend":
        return [
          { kind: "think", text: "围绕核心商品拓展日本市场在售样本" },
          { kind: "think", text: "评估同款竞争热度与定价空间" },
          {
            kind: "metric",
            text: counters.image_search_entries ? "市场样本拓展完成" : "正在拓展市场样本…",
          },
        ];
      case "risk":
        return [
          { kind: "think", text: "多维风控：禁运禁售 · 专利商标 · 海关报关 · 平台限售" },
          { kind: "metric", text: eliminated.e ? "高风险商品已剔除" : "正在剔除高风险商品…" },
        ];
      case "blue":
        return [
          { kind: "think", text: "比对平台爆款热度，规避红海竞争" },
          { kind: "metric", text: counters.candidates ? "低竞争机会已锁定" : "正在锁定低竞争机会…" },
        ];
      case "report":
        return [
          {
            kind: "think",
            text: "AI 撰写市场机会报告：类目调研 / 产品定位 / 目标受众 / 风险 / 限售标注",
          },
          { kind: "metric", text: allDone ? "报告已生成，点右上角查看" : "报告生成中…" },
        ];
      case "final":
        return [
          { kind: "think", text: "综合稳健、亮点、趋势等多维度精选可上架商品" },
          { kind: "metric", text: finalItems.length ? "最终商品已出炉" : "正在精选最终商品…" },
        ];
      default:
        return [];
    }
  }

  function renderStageBody(key: string) {
    if (key === "keyword") {
      const previewLimit = 12;
      const canCollapse = keywords.length > previewLimit;
      const visible = showAllKeywords || !canCollapse ? keywords : keywords.slice(0, previewLimit);
      return keywords.length ? (
        <div className="sel-chips">
          {visible.map((k, i) => (
            <span
              className="sel-chip"
              key={String(k.id || i)}
              style={{ animationDelay: `${i * 0.02}s` }}
            >
              {String(k.keyword)}
            </span>
          ))}
          {canCollapse && !showAllKeywords && (
            <button
              type="button"
              className="sel-chips-toggle"
              onClick={(e) => {
                e.stopPropagation();
                setShowAllKeywords(true);
              }}
            >
              +{keywords.length - previewLimit} 个更多
            </button>
          )}
          {canCollapse && showAllKeywords && (
            <button
              type="button"
              className="sel-chips-toggle ghost"
              onClick={(e) => {
                e.stopPropagation();
                setShowAllKeywords(false);
              }}
            >
              收起
            </button>
          )}
        </div>
      ) : (
        <div className="sel-wait">AI 正在拆解需求，识别潜力类目…</div>
      );
    }
    if (key === "supplier") {
      return liveGroups.length ? (
        <div className="sel-reels">
          {liveGroups.slice(0, 12).map((g) => (
            <div className="sel-reel-row" key={g.keyword_id}>
              <span className="sel-reel-kw" title={String(g.keyword)}>
                {String(g.keyword)}
              </span>
              <Reel items={g.items} tick={reelTick} />
            </div>
          ))}
        </div>
      ) : (
        <div className="sel-wait">正在匹配优质产业带货源…</div>
      );
    }
    if (key === "trend") {
      return echotik.length ? (
        <>
          {hasSupplyFallback && (
            <div className="sel-source-note">
              当前基于供应链样本数据估算，销量口径为批发侧样本，非日本站实测数据，建议上架前二次验证。
            </div>
          )}
          <div className="sel-echo">
            {echotik.map((it, i) => {
              const key = String(it.id || it.title || i);
              const url = item1688Url(it);
              return (
                <a
                  className="sel-echo-card"
                  key={key}
                  href={url || undefined}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div className="sel-echo-img">
                    {it.image_url ? (
                      <img src={String(it.image_url)} alt="" />
                    ) : (
                      <span>无图</span>
                    )}
                  </div>
                </a>
              );
            })}
          </div>
        </>
      ) : (
        <div className="sel-wait">正在拓展日本市场在售样本…</div>
      );
    }
    if (key === "risk") {
      return eliminated.e ? (
        <div className="sel-elim">
          {liveGroups
            .flatMap((g) => g.items.filter((it) => it.eliminated).slice(0, 2))
            .slice(0, 4)
            .map((it, i) => (
              <div className="sel-elim-row" key={i}>
                <span className="x">×</span>
                <b>{String(it.title || "高风险商品")}</b>
              </div>
            ))}
        </div>
      ) : (
        <div className="sel-wait">尚未发现高风险商品…</div>
      );
    }
    if (key === "final") {
      return finalItems.length ? (
        <>
          {hasSupplyFallback && (
            <div className="sel-source-note">
              当前基于供应链样本数据估算，销量口径为批发侧样本，非日本站实测数据，建议上架前二次验证。
            </div>
          )}
          <div className="sel-final-grid">
            {finalItems.slice(0, 10).map((it, i) => {
              const key = String(it.id || it.title || i);
              const url = item1688Url(it);
              return (
                <a
                  className="sel-final-card"
                  key={key}
                  href={url || undefined}
                  target="_blank"
                  rel="noreferrer"
                  title={String(it.title || `商品 ${i + 1}`)}
                >
                  <span className={`sel-final-badge ${String(it.tier || "regular")}`}>
                    {TIER_LABEL[String(it.tier || "regular")] || "常规"}
                  </span>
                  <div className="sel-final-img">
                    {it.image_url ? (
                      <img src={String(it.image_url)} alt="" />
                    ) : (
                      <span>{i + 1}</span>
                    )}
                  </div>
                  <b>{String(it.title || `商品 ${i + 1}`)}</b>
                  <small>{String(it.shop_name || "优选供应商")}</small>
                  {it.highlight_reason ? (
                    <em className="sel-final-reason">{String(it.highlight_reason)}</em>
                  ) : null}
                </a>
              );
            })}
          </div>
        </>
      ) : (
        <div className="sel-wait">正在汇总精选商品…</div>
      );
    }
    return null;
  }

  return (
    <div className="sel-timeline">
      {steps.map((step, idx) => {
        const done = idx < currentStep || allDone;
        const active =
          (idx === currentStep && status === "running") ||
          (allDone && idx === 6);
        const isOpen = !!expanded[idx];
        if (!active) {
          return (
            <div
              className={`sel-step ${done ? "done" : "pending"} ${isOpen ? "open" : ""}`}
              key={step.key}
            >
              <button
                type="button"
                className="sel-step-toggle"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }))
                }
                aria-expanded={isOpen}
              >
                <span className="sel-dot">{done ? "✓" : step.icon}</span>
                <div className="sel-step-row">
                  <span className="sel-caret">{isOpen ? "▾" : "▸"}</span>
                  <b>{step.title}</b>
                  <span className="sel-sum">{done ? summaryFor(idx) : "待执行"}</span>
                </div>
              </button>
              {isOpen && (
                <div className="sel-step-card">
                  <div className="sel-lines">
                    {linesFor(step.key).map((ln, i) => (
                      <div
                        className={`sel-line ${ln.kind}`}
                        key={i}
                        style={{ animationDelay: `${i * 0.12}s` }}
                      >
                        <span className="d" />
                        <span>{ln.text}</span>
                      </div>
                    ))}
                  </div>
                  {renderStageBody(step.key)}
                </div>
              )}
            </div>
          );
        }
        const lines = linesFor(step.key);
        return (
          <div className="sel-step active" key={step.key}>
            <span className="sel-dot live">{step.icon}</span>
            <div className="sel-step-card">
              <div className="sel-step-head">
                <b>{step.title}</b>
                <span className="sel-badge">{allDone ? "已完成" : "进行中"}</span>
              </div>
              <div className="sel-lines">
                {lines.map((ln, i) => (
                  <div
                    className={`sel-line ${ln.kind}`}
                    key={i}
                    style={{ animationDelay: `${i * 0.12}s` }}
                  >
                    <span className="d" />
                    <span>{ln.text}</span>
                  </div>
                ))}
              </div>
              {renderStageBody(step.key)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DerivationStage(props: {
  status: string;
  currentStep: number;
  reportData: PipelineReportData | null;
  counters: Record<string, number>;
  groups: Array<{ keyword_id: number; keyword: string; items: Array<Record<string, unknown>> }>;
}) {
  const { status, currentStep, reportData, counters, groups } = props;
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [showAllKeywords, setShowAllKeywords] = useState(false);

  useEffect(() => {
    if (status === "idle") {
      setExpanded({});
      setShowAllKeywords(false);
    }
  }, [status]);

  const allDone = status === "success";
  const liveGroups = useMemo(
    () => groups.filter((g) => g.keyword_id !== -1 && g.keyword_id !== -2),
    [groups],
  );
  const eliminated = useMemo(() => {
    let e = 0, k = 0;
    for (const g of liveGroups)
      for (const it of g.items) {
        if (it.eliminated) e++;
        else k++;
      }
    return { e, k };
  }, [liveGroups]);
  const echotik = useMemo(
    () => (reportData?.board_items || []).filter((b: Record<string, unknown>) => b.source === "echotik" || b.source === "supply_fallback").slice(0, 8),
    [reportData],
  );
  const hasSupplyFallback = useMemo(
    () => (reportData?.board_items || []).some((b: Record<string, unknown>) => b.source === "supply_fallback"),
    [reportData],
  );
  const finalItems = useMemo(
    () => Array.isArray(reportData?.final_items) ? reportData.final_items : [],
    [reportData],
  );
  const keywords = useMemo(
    () => Array.isArray(reportData?.keywords) ? reportData.keywords as Array<Record<string, unknown>> : [],
    [reportData],
  );

  const steps = [
    { key: "keyword", title: "AI 生成衍生方向", icon: "💡" },
    { key: "supplier", title: "匹配优质供应链", icon: "🔗" },
    { key: "trend", title: "拓展市场在售样本", icon: "🌐" },
    { key: "risk", title: "日本法规风控", icon: "🛡" },
    { key: "blue", title: "蓝海竞争过滤", icon: "🌊" },
    { key: "report", title: "生成可视化报告", icon: "📊" },
    { key: "final", title: "精选最终 10 款", icon: "🏆" },
  ];

  function summaryFor(idx: number): string {
    switch (idx) {
      case 0:
        return keywords.length ? "衍生方向已生成" : "正在生成衍生方向";
      case 1:
        return counters.supplier_candidates ? "货源匹配完成" : "正在匹配供应链";
      case 2:
        return counters.image_search_entries ? "市场样本拓展完成" : "正在拓展市场样本";
      case 3:
        return eliminated.e !== undefined ? "风控审核完成" : "正在多维风控审核";
      case 4:
        return counters.candidates ? "蓝海机会识别完成" : "正在识别蓝海机会";
      case 5:
        return allDone ? "报告已生成" : "报告生成中";
      case 6:
        return finalItems.length ? "精选商品已出炉" : "正在精选最终商品";
      default:
        return "";
    }
  }

  function linesFor(key: string): Array<{ kind: string; text: string }> {
    switch (key) {
      case "keyword":
        return [
          { kind: "think", text: "解析原商品属性，识别目标人群与使用场景" },
          { kind: "think", text: "基于商品族特征生成差异化衍生方向" },
          { kind: "metric", text: keywords.length ? `${keywords.length} 个衍生方向已生成` : "正在生成衍生方向…" },
        ];
      case "supplier":
        return [
          { kind: "think", text: "针对每个衍生方向定向匹配 1688 优质产业带" },
          { kind: "think", text: "评估供应稳定性、价格带与起订能力" },
          { kind: "metric", text: counters.supplier_candidates ? `${counters.supplier_candidates} 个供应链样本已锁定` : "正在锁定货源基准…" },
        ];
      case "trend":
        return [
          { kind: "think", text: "围绕核心衍生款拓展日本市场在售样本" },
          { kind: "think", text: "评估同款竞争热度与定价空间" },
          { kind: "metric", text: counters.image_search_entries ? "市场样本拓展完成" : "正在拓展市场样本…" },
        ];
      case "risk":
        return [
          { kind: "think", text: "多维风控：禁运禁售 · 专利商标 · 海关报关 · 平台限售" },
          { kind: "metric", text: eliminated.e ? `${eliminated.e} 个高风险商品已剔除` : "正在剔除高风险商品…" },
        ];
      case "blue":
        return [
          { kind: "think", text: "比对平台爆款热度，规避红海竞争" },
          { kind: "metric", text: counters.candidates ? `${counters.candidates} 个低竞争机会已锁定` : "正在锁定低竞争机会…" },
        ];
      case "report":
        return [
          { kind: "think", text: "AI 撰写衍生品市场机会报告：定位 / 受众 / 风险 / 上架建议" },
          { kind: "metric", text: allDone ? "报告已生成，点右上角查看" : "报告生成中…" },
        ];
      case "final":
        return [
          { kind: "think", text: "综合稳健、亮点、趋势等多维度精选可上架商品" },
          { kind: "metric", text: finalItems.length ? `${finalItems.length} 款最终商品已出炉` : "正在精选最终商品…" },
        ];
      default:
        return [];
    }
  }

  function renderStageBody(key: string) {
    if (key === "keyword") {
      const previewLimit = 12;
      const canCollapse = keywords.length > previewLimit;
      const visible = showAllKeywords || !canCollapse ? keywords : keywords.slice(0, previewLimit);
      return keywords.length ? (
        <div className="sel-chips">
          {visible.map((k, i) => (
            <span
              className="sel-chip"
              key={String(k.id || i)}
              style={{ animationDelay: `${i * 0.02}s` }}
            >
              {String(k.keyword)}
            </span>
          ))}
          {canCollapse && !showAllKeywords && (
            <button
              type="button"
              className="sel-chips-toggle"
              onClick={(e) => {
                e.stopPropagation();
                setShowAllKeywords(true);
              }}
            >
              +{keywords.length - previewLimit} 个更多
            </button>
          )}
          {canCollapse && showAllKeywords && (
            <button
              type="button"
              className="sel-chips-toggle ghost"
              onClick={(e) => {
                e.stopPropagation();
                setShowAllKeywords(false);
              }}
            >
              收起
            </button>
          )}
        </div>
      ) : (
        <div className="sel-wait">AI 正在拆解原商品，生成衍生方向…</div>
      );
    }
    if (key === "supplier") {
      return liveGroups.length ? (
        <div className="sel-reels">
          {liveGroups.slice(0, 12).map((g) => (
            <div className="sel-reel-row" key={g.keyword_id}>
              <span className="sel-reel-kw" title={String(g.keyword)}>
                {String(g.keyword)}
              </span>
              <Reel items={g.items} tick={0} />
            </div>
          ))}
        </div>
      ) : (
        <div className="sel-wait">正在匹配优质产业带货源…</div>
      );
    }
    if (key === "trend") {
      return echotik.length ? (
        <>
          {hasSupplyFallback && (
            <div className="sel-source-note">
              当前基于供应链样本数据估算，销量口径为批发侧样本，非日本站实测数据，建议上架前二次验证。
            </div>
          )}
          <div className="sel-echo">
            {echotik.map((it, i) => {
              const key = String(it.id || it.title || i);
              const url = item1688Url(it);
              return (
                <a
                  className="sel-echo-card"
                  key={key}
                  href={url || undefined}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div className="sel-echo-img">
                    {it.image_url ? (
                      <img src={String(it.image_url)} alt="" />
                    ) : (
                      <span>无图</span>
                    )}
                  </div>
                </a>
              );
            })}
          </div>
        </>
      ) : (
        <div className="sel-wait">正在拓展日本市场在售样本…</div>
      );
    }
    if (key === "risk") {
      return eliminated.e ? (
        <div className="sel-elim">
          {liveGroups
            .flatMap((g) => g.items.filter((it) => it.eliminated).slice(0, 2))
            .slice(0, 4)
            .map((it, i) => (
              <div className="sel-elim-row" key={i}>
                <span className="x">×</span>
                <b>{String(it.title || "高风险商品")}</b>
              </div>
            ))}
        </div>
      ) : (
        <div className="sel-wait">尚未发现高风险商品…</div>
      );
    }
    if (key === "final") {
      return finalItems.length ? (
        <>
          {hasSupplyFallback && (
            <div className="sel-source-note">
              当前基于供应链样本数据估算，销量口径为批发侧样本，非日本站实测数据，建议上架前二次验证。
            </div>
          )}
          <div className="sel-final-grid">
            {finalItems.slice(0, 10).map((it, i) => {
              const key = String(it.id || it.title || i);
              const url = item1688Url(it);
              return (
                <a
                  className="sel-final-card"
                  key={key}
                  href={url || undefined}
                  target="_blank"
                  rel="noreferrer"
                  title={String(it.title || `商品 ${i + 1}`)}
                >
                  <span className={`sel-final-badge ${String(it.tier || "regular")}`}>
                    {TIER_LABEL[String(it.tier || "regular")] || "常规"}
                  </span>
                  <div className="sel-final-img">
                    {it.image_url ? (
                      <img src={String(it.image_url)} alt="" />
                    ) : (
                      <span>{i + 1}</span>
                    )}
                  </div>
                  <b>{String(it.title || `商品 ${i + 1}`)}</b>
                  <small>{String(it.shop_name || "优选供应商")}</small>
                  {it.highlight_reason ? (
                    <em className="sel-final-reason">{String(it.highlight_reason)}</em>
                  ) : null}
                </a>
              );
            })}
          </div>
        </>
      ) : (
        <div className="sel-wait">正在汇总精选商品…</div>
      );
    }
    return null;
  }

  if (status === "idle") {
    return (
      <div className="empty-state">
        点击「开始衍生」后，右侧将逐步呈现 AI 生成方向、供应链匹配、风控审核与最终精选报告。
      </div>
    );
  }

  return (
    <div className="sel-timeline">
      {steps.map((step, idx) => {
        const done = idx < currentStep || allDone;
        const active =
          (idx === currentStep && status === "running") ||
          (allDone && idx === 6);
        const isOpen = !!expanded[idx];
        if (!active) {
          return (
            <div
              className={`sel-step ${done ? "done" : "pending"} ${isOpen ? "open" : ""}`}
              key={step.key}
            >
              <button
                type="button"
                className="sel-step-toggle"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }))
                }
                aria-expanded={isOpen}
              >
                <span className="sel-dot">{done ? "✓" : step.icon}</span>
                <div className="sel-step-row">
                  <span className="sel-caret">{isOpen ? "▾" : "▸"}</span>
                  <b>{step.title}</b>
                  <span className="sel-sum">{done ? summaryFor(idx) : "待执行"}</span>
                </div>
              </button>
              {isOpen && (
                <div className="sel-step-card">
                  <div className="sel-lines">
                    {linesFor(step.key).map((ln, i) => (
                      <div
                        className={`sel-line ${ln.kind}`}
                        key={i}
                        style={{ animationDelay: `${i * 0.12}s` }}
                      >
                        <span className="d" />
                        <span>{ln.text}</span>
                      </div>
                    ))}
                  </div>
                  {renderStageBody(step.key)}
                </div>
              )}
            </div>
          );
        }
        const lines = linesFor(step.key);
        return (
          <div className="sel-step active" key={step.key}>
            <span className="sel-dot live">{step.icon}</span>
            <div className="sel-step-card">
              <div className="sel-step-head">
                <b>{step.title}</b>
                <span className="sel-badge">{allDone ? "已完成" : "进行中"}</span>
              </div>
              <div className="sel-lines">
                {lines.map((ln, i) => (
                  <div
                    className={`sel-line ${ln.kind}`}
                    key={i}
                    style={{ animationDelay: `${i * 0.12}s` }}
                  >
                    <span className="d" />
                    <span>{ln.text}</span>
                  </div>
                ))}
              </div>
              {renderStageBody(step.key)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SmartSelection({
  user,
  onNotice,
}: {
  user: User;
  onNotice: (message: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [taskId, setTaskId] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("created");
  const [status, setStatus] = useState<
    "idle" | "running" | "success" | "failed"
  >("idle");
  const [taskMessage, setTaskMessage] = useState("");
  const [groups, setGroups] = useState<
    Array<{
      keyword_id: number;
      keyword: string;
      items: Array<Record<string, unknown>>;
    }>
  >([]);
  const [keywords, setKeywords] = useState<Array<Record<string, unknown>>>([]);
  const [boardItems, setBoardItems] = useState<Array<Record<string, unknown>>>([]);
  const [counters, setCounters] = useState<Record<string, number>>({});
  const [lastTaskResult, setLastTaskResult] =
    useState<PipelineReportData | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [logs, setLogs] = useState<
    Array<{ time: string; step: number; message: string }>
  >([]);
  const displayedStageRef = useRef("");
  const displayedStageAtRef = useRef(0);

  const currentStep = useMemo(
    () =>
      stage in STAGE_MAP
        ? STAGE_MAP[stage]
        : Math.min(6, Math.floor(progress / 15)),
    [stage, progress],
  );

  const pushLog = useCallback((nextStage: string, nextMessage: string) => {
    const stepIndex = STAGE_MAP[nextStage] ?? -1;
    const label = stepIndex >= 0 ? FLOW_NODES[stepIndex]?.title : "任务初始化";
    const time = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setLogs((prev) => {
      const next = [
        ...prev,
        { time, step: stepIndex, message: nextMessage || label },
      ];
      return next.slice(-6);
    });
  }, []);

  async function applyTaskData(
    data: Record<string, any>,
    restoreInput = false,
  ) {
    const nextStage = String(data.stage || "created");
    const elapsed = Date.now() - displayedStageAtRef.current;
    if (
      displayedStageRef.current &&
      nextStage !== displayedStageRef.current &&
      elapsed < 1000
    ) {
      await new Promise((resolve) =>
        window.setTimeout(resolve, 1000 - elapsed),
      );
    }
    const stageChanged = nextStage !== displayedStageRef.current;
    if (stageChanged) {
      displayedStageRef.current = nextStage;
      displayedStageAtRef.current = Date.now();
    }
    const nextProgress = Number(data.progress || 0);
    const nextMessage = String(data.message || "");
    setProgress(nextProgress);
    setStage(nextStage);
    setTaskMessage(nextMessage);
    setCounters(data.counters || {});
    if (restoreInput && data.input_message)
      setMessage(String(data.input_message));
    const boardGroups = Array.isArray(data.board_groups)
      ? [...data.board_groups]
      : [];
    if (Array.isArray(data.candidate_items) && data.candidate_items.length)
      boardGroups.push({
        keyword_id: -1,
        keyword: "30 个候选蓝海商品",
        items: data.candidate_items,
      });
    if (Array.isArray(data.final_items) && data.final_items.length)
      boardGroups.push({
        keyword_id: -2,
        keyword: "10 个精选商品",
        items: data.final_items,
      });
    if (boardGroups.length) setGroups(boardGroups);
    if (Array.isArray(data.keywords)) setKeywords(data.keywords as Array<Record<string, unknown>>);
    if (Array.isArray(data.board_items)) setBoardItems(data.board_items as Array<Record<string, unknown>>);
    if (data.status === "success")
      setLastTaskResult(data as PipelineReportData);
    if (stageChanged) pushLog(nextStage, nextMessage);
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const storageKey = `tk_selection_pipeline_task_${user.id || user.username || "current"}`;
        const storedTaskId = Number(localStorage.getItem(storageKey) || 0);
        const latest = storedTaskId
          ? { task_id: storedTaskId }
          : await service.getLatestSelectionPipelineTask();
        if (!latest.task_id || cancelled) return;
        const data = await service.getSelectionPipelineTask(latest.task_id);
        if (cancelled) return;
        await applyTaskData(data, true);
        setStatus(
          data.status === "success"
            ? "success"
            : data.status === "failed"
              ? "failed"
              : "running",
        );
        if (data.status !== "success" && data.status !== "failed")
          setTaskId(Number(latest.task_id));
      } catch {
        // 没有历史任务或服务暂不可用时保持空白待开始状态。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user.id, user.username]);

  useEffect(() => {
    if (!taskId) return;
    const timer = window.setInterval(async () => {
      try {
        const data = await service.getSelectionPipelineTask(taskId);
        await applyTaskData(data);
        if (data.status === "success" || data.status === "failed") {
          window.clearInterval(timer);
          setStatus(data.status);
          setTaskId(null);
          if (data.status === "success")
            onNotice("选品任务完成，可导出候选品和精选品报告");
        }
      } catch (error) {
        window.clearInterval(timer);
        setTaskId(null);
        setStatus("failed");
        onNotice(error instanceof Error ? error.message : "任务查询失败");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [taskId]);

  const submit = useCallback(async () => {
    if (!message.trim() || taskId) return;
    try {
      setStatus("running");
      setProgress(1);
      setStage("created");
      setLastTaskResult(null);
      setTaskMessage("正在创建智能选品任务");
      setGroups([]);
      setKeywords([]);
      setBoardItems([]);
      setCounters({});
      setLogs([]);
      const result = await service.createSelectionPipelineTask(message.trim());
      if (!result.task_id) throw new Error("服务未返回任务编号");
      localStorage.setItem(
        `tk_selection_pipeline_task_${user.id || user.username || "current"}`,
        String(result.task_id),
      );
      setTaskId(Number(result.task_id));
    } catch (error) {
      setStatus("failed");
      onNotice(error instanceof Error ? error.message : "启动选品任务失败");
    }
  }, [message, taskId, user.id, user.username]);

  const exportReport = useCallback(async () => {
    if (!lastTaskResult?.id) return;
    try {
      onNotice("正在下载已生成的选品报告...");
      await downloadPipelineReport(lastTaskResult);
      onNotice("报告已生成并保存到下载目录");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "报告生成失败");
    }
  }, [lastTaskResult, onNotice]);

  return (
    <section className="smart-selection">
      <div className="smart-heading">
        <div>
          <h2>AI 智能选品</h2>
          <p>输入需求后，左侧执行七步严筛，右侧实时呈现货源与动态。</p>
        </div>
      </div>
      <div className="smart-workspace">
        <div className="smart-panel-left">
          <div className="smart-chat">
            <div className="smart-chat-title">
              <b>告诉我您想找什么样的产品？</b>
              <small>AI 选品助手</small>
            </div>
            <textarea
              value={message}
              maxLength={300}
              placeholder="输入选品需求，例如：日本 TikTok 夏季防晒蓝海商品"
              onChange={(event) => setMessage(event.target.value)}
              disabled={Boolean(taskId)}
            />
            <div className="smart-controls">
              <span>{message.length}/300</span>
              <button
                className="primary"
                disabled={!message.trim() || Boolean(taskId)}
                onClick={submit}
              >
                {taskId ? "执行中..." : "智能选品"}
              </button>
            </div>
            <div className="smart-hot-searches">
              <b>热门搜索：</b>
              {HOT_SEARCHES.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setMessage(item)}
                  disabled={Boolean(taskId)}
                >
                  {item}
                </button>
              ))}
            </div>
            {(status === "running" || status === "success") && (
              <div
                className={`smart-progress ${status === "running" ? "running" : ""}`}
              >
                <div>
                  <span>{taskMessage || "正在执行选品流程"}</span>
                  <b>{progress}%</b>
                </div>
                <i>
                  <em style={{ transform: `scaleX(${progress / 100})` }} />
                </i>
              </div>
            )}
          </div>
          <div className="selection-flow-panel">
            <div className="selection-flow-heading">
              <div>
                <h2>智能选品流程</h2>
                <p>
                  {status === "idle"
                    ? "点击智能选品后实时查看进度"
                    : `当前第 ${Math.max(1, currentStep + 1)} 步：${taskMessage || FLOW_NODES[Math.max(0, currentStep)]?.title || ""}`}
                </p>
              </div>
              <span className={`flow-status ${status}`}>
                {status === "success"
                  ? "已完成"
                  : status === "failed"
                    ? "失败"
                    : status === "running"
                      ? "执行中"
                      : "待开始"}
              </span>
            </div>
            <div className="selection-flow-row">
              {FLOW_NODES.map((node, index) => (
                <div
                  key={node.title}
                  className={`flow-node ${index < currentStep || status === "success" ? "done" : index === currentStep && status === "running" ? "active running" : ""}`}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <b>{node.title}</b>
                    <small>{node.description}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <aside className="smart-panel-right task-board-panel">
            <div className="task-board-header">
            <h2>任务结果看板</h2>
            <div className="task-board-header-actions">
              {status === "success" && lastTaskResult && (
                <>
                  <button
                    className="primary small"
                    onClick={() => setReportOpen(true)}
                  >
                    查看完整市场机会报告
                  </button>
                  <span className="task-board-auto-hint">已自动加入选品库</span>
                </>
              )}
            </div>
          </div>
          <div className="task-board-logs">
            <h4>实时动态</h4>
            {logs.length ? (
              logs.slice(-3).map((log, idx) => (
                <div
                  key={`${log.time}-${idx}`}
                  className={`task-board-log ${idx === logs.length - 1 && status === "running" ? "current" : ""}`}
                >
                  <i />
                  <time>{log.time}</time>
                  <span>{log.message}</span>
                </div>
              ))
            ) : (
              <div className="task-board-log">
                <i />
                <span>等待任务开始…</span>
              </div>
            )}
          </div>
          <div className="task-board-body">
            <SelectionStage
              status={status}
              currentStep={currentStep}
              keywords={keywords}
              groups={groups}
              counters={counters}
              boardItems={boardItems}
              finalItems={lastTaskResult ? (lastTaskResult.final_items || []) : []}
            />
          </div>
        </aside>
      </div>
      {reportOpen && lastTaskResult && (
        <SelectionReport
          data={lastTaskResult}
          onClose={() => setReportOpen(false)}
        />
      )}
    </section>
  );
}

type AdminTab = "users" | "models" | "third" | "settings" | "releases";

function AdminConsoleLegacy({ notice }: { notice: (s: string) => void }) {
  const tabs: Array<{ id: AdminTab; label: string }> = [
    { id: "users", label: "用户管理" },
    { id: "models", label: "模型配置" },
    { id: "third", label: "第三方 API" },
    { id: "settings", label: "业务配置" },
    { id: "releases", label: "版本更新" },
  ];
  const [tab, setTab] = useState<AdminTab>("users");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [releaseFile, setReleaseFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [releaseMeta, setReleaseMeta] = useState({
    version: "",
    release_notes: "",
    force_update: false,
  });

  async function load() {
    try {
      const data =
        tab === "users"
          ? await service.getUsers()
          : tab === "models"
            ? await service.getModelConfigs()
            : tab === "third"
              ? await service.getThirdPartyConfigs()
              : tab === "settings"
                ? await service.getSystemSettings()
                : await service.getAppReleases();
      setRows(
        Array.isArray(data)
          ? (data as Record<string, unknown>[])
          : Object.entries(data).map(([key, value]) => ({
              setting_key: key,
              setting_value: String(value ?? ""),
            })),
      );
    } catch (error) {
      notice(error instanceof Error ? error.message : "读取管理数据失败");
    }
  }
  useEffect(() => {
    void load();
  }, [tab]);
  function startEdit(row: Record<string, unknown> = {}) {
    setEditing(true);
    const base: Record<string, string> = row.id ? { id: String(row.id) } : {};
    if (tab === "users")
      setForm({
        ...base,
        username: String(row.username || ""),
        password: "",
        real_name: String(row.real_name || ""),
        role: String(row.role || "student"),
        status: String(row.status ?? 1),
      });
    if (tab === "models")
      setForm({
        ...base,
        config_name: String(row.config_name || ""),
        provider: String(row.provider || "custom"),
        model_type: String(row.model_type || "general"),
        base_url: String(row.base_url || ""),
        api_key_encrypted: String(row.api_key_encrypted || ""),
        model_name: String(row.model_name || ""),
        temperature: String(row.temperature ?? "0.2"),
        max_tokens: String(row.max_tokens ?? "4000"),
        status: String(row.status ?? 1),
        remark: String(row.remark || ""),
      });
    if (tab === "third")
      setForm({
        ...base,
        config_name: String(row.config_name || ""),
        service_type: String(row.service_type || "custom_api"),
        api_base_url: String(row.api_base_url || ""),
        access_key_encrypted: String(row.access_key_encrypted || ""),
        secret_key_encrypted: String(row.secret_key_encrypted || ""),
        db_host: String(row.db_host || ""),
        db_port: String(row.db_port || ""),
        db_name: String(row.db_name || ""),
        db_user: String(row.db_user || ""),
        db_password_encrypted: String(row.db_password_encrypted || ""),
        sign_name: String(row.sign_name || ""),
        template_code: String(row.template_code || ""),
        status: String(row.status ?? 1),
        remark: String(row.remark || ""),
      });
    if (tab === "settings")
      setForm({
        ...base,
        setting_key: String(row.setting_key || ""),
        setting_value: String(row.setting_value || ""),
      });
  }
  function closeEdit() {
    setEditing(false);
    setForm({});
  }
  async function save() {
    setBusy(true);
    try {
      const id = Number(form.id || 0);
      if (tab === "users") {
        const payload = {
          username: form.username,
          password: form.password || "123456",
          real_name: form.real_name,
          role: form.role,
          status: Number(form.status || 1),
        };
        id
          ? await service.updateUser(id, payload)
          : await service.createUser(payload);
      }
      if (tab === "models") {
        const payload = {
          ...form,
          temperature: Number(form.temperature || 0.2),
          max_tokens: Number(form.max_tokens || 4000),
          status: Number(form.status || 1),
        };
        id
          ? await service.updateModelConfig(id, payload)
          : await service.createModelConfig(payload);
      }
      if (tab === "third") {
        const payload = {
          ...form,
          db_port: form.db_port ? Number(form.db_port) : null,
          status: Number(form.status || 1),
        };
        id
          ? await service.updateThirdPartyConfig(id, payload)
          : await service.createThirdPartyConfig(payload);
      }
      if (tab === "settings")
        await service.updateSystemSettings({
          [form.setting_key]: form.setting_value,
        });
      closeEdit();
      await load();
      notice("保存成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(row: Record<string, unknown>) {
    const id = Number(row.id);
    const status = Number(row.status) === 1 ? 0 : 1;
    try {
      if (tab === "users") await service.setUserStatus(id, status);
      if (tab === "models") await service.setModelStatus(id, status);
      if (tab === "third") await service.setThirdPartyStatus(id, status);
      await load();
    } catch (error) {
      notice(error instanceof Error ? error.message : "状态更新失败");
    }
  }
  async function remove(row: Record<string, unknown>) {
    const id = Number(row.id);
    if (!id || !window.confirm("确定删除这条配置吗？")) return;
    try {
      if (tab === "users") await service.deleteUser(id);
      if (tab === "models") await service.deleteModelConfig(id);
      if (tab === "third") await service.deleteThirdPartyConfig(id);
      if (tab === "releases") await service.deleteAppRelease(id);
      await load();
      notice("删除成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "删除失败");
    }
  }
  async function recharge(row: Record<string, unknown>) {
    const value = Number(window.prompt("请输入充值积分", "100") || 0);
    if (!value) return;
    try {
      await service.rechargeUser(Number(row.id), value, "管理员充值");
      await load();
      notice("充值成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "充值失败");
    }
  }
  async function testModel(row: Record<string, unknown>) {
    try {
      setBusy(true);
      const result = await service.testModelConfig(
        Number(row.id),
        "请用一句话介绍你自己",
      );
      notice(
        `模型测试完成：${String(result?.content || result?.answer || "已返回结果").slice(0, 80)}`,
      );
    } catch (error) {
      notice(error instanceof Error ? error.message : "模型测试失败");
    } finally {
      setBusy(false);
    }
  }
  async function uploadRelease() {
    if (!releaseFile || !releaseMeta.version) {
      notice("请填写版本号并选择安装包");
      return;
    }
    try {
      setBusy(true);
      await service.uploadAppRelease({ ...releaseMeta, package: releaseFile });
      setReleaseFile(null);
      setReleaseMeta({ version: "", release_notes: "", force_update: false });
      await load();
      notice("版本发布成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "版本发布失败");
    } finally {
      setBusy(false);
    }
  }
  function field(label: string, key: string, type = "text") {
    return (
      <label className="admin-field">
        {label}
        <input
          type={type}
          value={form[key] || ""}
          onChange={(event) =>
            setForm((current) => ({ ...current, [key]: event.target.value }))
          }
        />
      </label>
    );
  }
  const actionButtons = (row: Record<string, unknown>) => (
    <div className="admin-actions">
      <button onClick={() => startEdit({ ...row, id: row.id })}>编辑</button>
      {["users", "models", "third"].includes(tab) && (
        <button onClick={() => void toggle(row)}>
          {Number(row.status) === 1 ? "停用" : "启用"}
        </button>
      )}
      {tab === "users" && (
        <button onClick={() => void recharge(row)}>充值</button>
      )}
      {tab === "models" && (
        <button onClick={() => void testModel(row)}>测试</button>
      )}
      {["users", "models", "third", "releases"].includes(tab) && (
        <button className="danger-text" onClick={() => void remove(row)}>
          删除
        </button>
      )}
    </div>
  );
  return (
    <section className="admin-console">
      <div className="admin-console-head">
        <div>
          <h2>系统管理</h2>
          <p>集中管理账号、模型、第三方接口、业务阈值和版本发布。</p>
        </div>
        <button className="secondary" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <div className="admin-tabs">
        {tabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "active" : ""}
            onClick={() => {
              setTab(item.id);
              closeEdit();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "releases" ? (
        <div className="release-upload">
          <div>
            <b>发布新版本</b>
            <span>支持 .exe 或 .zip 安装包</span>
          </div>
          <input
            value={releaseMeta.version}
            onChange={(e) =>
              setReleaseMeta((v) => ({ ...v, version: e.target.value }))
            }
            placeholder="版本号，例如 1.0.3"
          />
          <input
            value={releaseMeta.release_notes}
            onChange={(e) =>
              setReleaseMeta((v) => ({ ...v, release_notes: e.target.value }))
            }
            placeholder="更新说明"
          />
          <input
            type="file"
            accept=".exe,.zip"
            onChange={(e) => setReleaseFile(e.target.files?.[0] || null)}
          />
          <label className="release-check">
            <input
              type="checkbox"
              checked={releaseMeta.force_update}
              onChange={(e) =>
                setReleaseMeta((v) => ({
                  ...v,
                  force_update: e.target.checked,
                }))
              }
            />{" "}
            强制更新
          </label>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void uploadRelease()}
          >
            上传并发布
          </button>
        </div>
      ) : (
        <button className="primary admin-add" onClick={() => startEdit()}>
          ＋ 新增{tabs.find((x) => x.id === tab)?.label}
        </button>
      )}
      <div className="admin-table">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>状态</th>
              <th>信息</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.id || index)}>
                <td>
                  {String(
                    row.real_name ||
                      row.username ||
                      row.config_name ||
                      row.setting_name ||
                      row.version ||
                      row.setting_key ||
                      "-",
                  )}
                </td>
                <td>
                  {String(
                    row.role ||
                      row.model_type ||
                      row.service_type ||
                      row.value_type ||
                      "-",
                  )}
                </td>
                <td>
                  {row.status === 1 || row.status === true
                    ? "启用"
                    : row.status === 0 || row.status === false
                      ? "停用"
                      : "-"}
                </td>
                <td>
                  {String(
                    row.model_name ||
                      row.provider ||
                      row.filename ||
                      row.setting_value ||
                      row.release_notes ||
                      row.description ||
                      "-",
                  )}
                </td>
                <td>
                  {tab === "settings" ? (
                    <button onClick={() => startEdit(row)}>编辑</button>
                  ) : (
                    actionButtons(row)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <div className="empty-state">暂无数据</div>}
      </div>
      {editing && (
        <div className="admin-editor">
          <div className="admin-editor-head">
            <h3>{form.id ? "编辑配置" : "新增配置"}</h3>
            <button onClick={closeEdit}>×</button>
          </div>
          <div className="admin-form-grid">
            {tab === "users" && (
              <>
                {field("账号", "username")}
                {field("姓名", "real_name")}
                {field("初始密码", "password", "password")}
                <label className="admin-field">
                  角色
                  <select
                    value={form.role || "student"}
                    onChange={(e) =>
                      setForm((v) => ({ ...v, role: e.target.value }))
                    }
                  >
                    <option value="student">学生</option>
                    <option value="teacher">老师</option>
                    <option value="admin">管理员</option>
                  </select>
                </label>
              </>
            )}
            {tab === "models" && (
              <>
                {field("配置名称", "config_name")}
                {field("服务商", "provider")}
                {field("模型类型", "model_type")}
                {field("Base URL", "base_url")}
                {field("API Key", "api_key_encrypted", "password")}
                {field("模型名称", "model_name")}
                {field("温度", "temperature", "number")}
                {field("最大输出", "max_tokens", "number")}
              </>
            )}
            {tab === "third" && (
              <>
                {field("配置名称", "config_name")}
                {field("服务类型", "service_type")}
                {field("API Base URL", "api_base_url")}
                {field("Access Key", "access_key_encrypted", "password")}
                {field("Secret Key", "secret_key_encrypted", "password")}
                {field("签名名称", "sign_name")}
                {field("短信模板", "template_code")}
                {field("数据库地址", "db_host")}
                {field("数据库端口", "db_port", "number")}
              </>
            )}
            {tab === "settings" && (
              <>
                {field("配置键", "setting_key")}
                {field("配置值", "setting_value")}
              </>
            )}
          </div>
          <div className="admin-editor-actions">
            <button className="secondary" onClick={closeEdit}>
              取消
            </button>
            <button
              className="primary"
              disabled={busy}
              onClick={() => void save()}
            >
              保存
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

type CompleteAdminTab =
  | "users"
  | "models"
  | "third"
  | "settings"
  | "attributes"
  | "prompts"
  | "restrictions"
  | "releases";

function AdminConsole({ notice }: { notice: (s: string) => void }) {
  const tabs: Array<{ id: CompleteAdminTab; label: string }> = [
    { id: "users", label: "用户管理" },
    { id: "models", label: "模型配置" },
    { id: "third", label: "第三方 API" },
    { id: "settings", label: "业务配置" },
    { id: "attributes", label: "选品属性" },
    { id: "prompts", label: "提示词常量" },
    { id: "restrictions", label: "日本限售规则" },
    { id: "releases", label: "版本更新" },
  ];
  const [tab, setTab] = useState<CompleteAdminTab>("users");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [releaseFile, setReleaseFile] = useState<File | null>(null);
  const [release, setRelease] = useState({
    version: "",
    release_notes: "",
    force_update: false,
  });
  const setField = (key: string, value: string) =>
    setForm((current) => ({ ...(current || {}), [key]: value }));
  const field = (label: string, key: string, type = "text") => (
    <label className="admin-field">
      {label}
      <input
        type={type}
        value={form?.[key] || ""}
        onChange={(e) => setField(key, e.target.value)}
      />
    </label>
  );

  async function load() {
    try {
      const data =
        tab === "users"
          ? await service.getUsers()
          : tab === "models"
            ? await service.getModelConfigs()
            : tab === "third"
              ? await service.getThirdPartyConfigs()
              : tab === "settings"
                ? await service.getSystemSettings()
                : tab === "attributes"
                  ? await service.getSelectionAttributesAdmin()
                  : tab === "prompts"
                    ? await service.getPromptConstants()
                    : tab === "restrictions"
                      ? await service.getRestrictionRules()
                      : await service.getAppReleases();
      setRows(
        Array.isArray(data)
          ? (data as Record<string, unknown>[])
          : Object.entries(data).map(([setting_key, setting_value]) => ({
              setting_key,
              setting_value: String(setting_value ?? ""),
            })),
      );
    } catch (error) {
      notice(error instanceof Error ? error.message : "读取管理数据失败");
    }
  }
  useEffect(() => {
    void load();
  }, [tab]);
  function edit(row: Record<string, unknown> = {}) {
    const base: Record<string, string> = row.id ? { id: String(row.id) } : {};
    if (tab === "users")
      setForm({
        ...base,
        username: String(row.username || ""),
        real_name: String(row.real_name || ""),
        password: "",
        role: String(row.role || "student"),
        status: String(row.status ?? 1),
      });
    else if (tab === "models")
      setForm({
        ...base,
        config_name: String(row.config_name || ""),
        provider: String(row.provider || "custom"),
        model_type: String(row.model_type || "general"),
        base_url: String(row.base_url || ""),
        api_key_encrypted: String(row.api_key_encrypted || ""),
        model_name: String(row.model_name || ""),
        temperature: String(row.temperature ?? "0.2"),
        max_tokens: String(row.max_tokens ?? "4000"),
        remark: String(row.remark || ""),
        status: String(row.status ?? 1),
      });
    else if (tab === "third")
      setForm({
        ...base,
        config_name: String(row.config_name || ""),
        service_type: String(row.service_type || "custom_api"),
        api_base_url: String(row.api_base_url || ""),
        access_key_encrypted: String(row.access_key_encrypted || ""),
        secret_key_encrypted: String(row.secret_key_encrypted || ""),
        db_host: String(row.db_host || ""),
        db_port: String(row.db_port || ""),
        db_name: String(row.db_name || ""),
        db_user: String(row.db_user || ""),
        db_password_encrypted: String(row.db_password_encrypted || ""),
        sign_name: String(row.sign_name || ""),
        template_code: String(row.template_code || ""),
        remark: String(row.remark || ""),
        status: String(row.status ?? 1),
      });
    else if (tab === "settings")
      setForm({
        ...base,
        setting_key: String(row.setting_key || ""),
        setting_value: String(row.setting_value || ""),
      });
    else if (tab === "attributes")
      setForm({
        ...base,
        attribute_name: String(row.attribute_name || row.name || ""),
        attribute_code: String(row.attribute_code || ""),
        attribute_type: String(row.attribute_type || "other"),
        description: String(row.description || ""),
        default_weight: String(row.default_weight ?? "1"),
        status: String(row.status ?? 1),
      });
    else if (tab === "prompts")
      setForm({
        ...base,
        constant_key: String(row.constant_key || ""),
        constant_name: String(row.constant_name || ""),
        constant_content: String(row.constant_content || ""),
        remark: String(row.remark || ""),
        status: String(row.status ?? 1),
      });
    else if (tab === "restrictions")
      setForm({
        ...base,
        rule_code: String(row.rule_code || ""),
        region: String(row.region || "JP"),
        category_keyword: String(row.category_keyword || ""),
        title_keyword: String(row.title_keyword || ""),
        action: String(row.action || "restricted"),
        reason: String(row.reason || ""),
        status: String(row.status ?? 1),
      });
  }
  async function save() {
    if (!form) return;
    setBusy(true);
    try {
      const id = Number(form.id || 0);
      const status = Number(form.status || 1);
      if (tab === "users") {
        const p = {
          username: form.username,
          password: form.password || "123456",
          real_name: form.real_name,
          role: form.role,
          status,
        };
        id ? await service.updateUser(id, p) : await service.createUser(p);
      }
      if (tab === "models") {
        const p = {
          ...form,
          temperature: Number(form.temperature || 0.2),
          max_tokens: Number(form.max_tokens || 4000),
          status,
        };
        id
          ? await service.updateModelConfig(id, p)
          : await service.createModelConfig(p);
      }
      if (tab === "third") {
        const p = {
          ...form,
          db_port: form.db_port ? Number(form.db_port) : null,
          status,
        };
        id
          ? await service.updateThirdPartyConfig(id, p)
          : await service.createThirdPartyConfig(p);
      }
      if (tab === "settings")
        await service.updateSystemSettings({
          [form.setting_key]: form.setting_value,
        });
      if (tab === "attributes") {
        const p = {
          ...form,
          default_weight: Number(form.default_weight || 1),
          status,
        };
        id
          ? await service.updateSelectionAttribute(id, p)
          : await service.createSelectionAttribute(p);
      }
      if (tab === "prompts") {
        const p = { ...form, status };
        id
          ? await service.updatePromptConstant(id, p)
          : await service.createPromptConstant(p);
      }
      if (tab === "restrictions") {
        const p = { ...form, status };
        id
          ? await service.updateRestrictionRule(id, p)
          : await service.createRestrictionRule(p);
      }
      setForm(null);
      await load();
      notice("保存成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(row: Record<string, unknown>) {
    const id = Number(row.id);
    const status = Number(row.status) === 1 ? 0 : 1;
    try {
      if (tab === "users") await service.setUserStatus(id, status);
      else if (tab === "models") await service.setModelStatus(id, status);
      else if (tab === "third") await service.setThirdPartyStatus(id, status);
      else if (tab === "attributes")
        await service.setSelectionAttributeStatus(id, status);
      else if (tab === "prompts")
        await service.setPromptConstantStatus(id, status);
      else if (tab === "restrictions")
        await service.updateRestrictionRule(id, {
          rule_code: row.rule_code || "",
          region: row.region || "JP",
          category_keyword: row.category_keyword || "",
          title_keyword: row.title_keyword || "",
          action: row.action || "restricted",
          reason: row.reason || "",
          status,
        });
      await load();
    } catch (error) {
      notice(error instanceof Error ? error.message : "状态更新失败");
    }
  }
  async function remove(row: Record<string, unknown>) {
    const id = Number(row.id);
    if (!id || !window.confirm("确定删除这条记录吗？")) return;
    try {
      if (tab === "users") await service.deleteUser(id);
      else if (tab === "models") await service.deleteModelConfig(id);
      else if (tab === "third") await service.deleteThirdPartyConfig(id);
      else if (tab === "attributes") await service.deleteSelectionAttribute(id);
      else if (tab === "prompts") await service.deletePromptConstant(id);
      else if (tab === "restrictions") await service.deleteRestrictionRule(id);
      else if (tab === "releases") await service.deleteAppRelease(id);
      await load();
      notice("删除成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "删除失败");
    }
  }
  async function recharge(row: Record<string, unknown>) {
    const amount = Number(window.prompt("请输入充值积分", "100") || 0);
    if (!amount) return;
    try {
      await service.rechargeUser(Number(row.id), amount, "管理员充值");
      await load();
      notice("充值成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "充值失败");
    }
  }
  async function resetPassword(row: Record<string, unknown>) {
    const password = window.prompt("请输入新密码", "123456");
    if (password === null) return;
    try {
      await service.resetUserPassword(Number(row.id), password || "123456");
      notice("密码已重置");
    } catch (error) {
      notice(error instanceof Error ? error.message : "密码重置失败");
    }
  }
  async function uploadRelease() {
    if (!releaseFile || !release.version)
      return notice("请填写版本号并选择安装包");
    try {
      setBusy(true);
      await service.uploadAppRelease({ ...release, package: releaseFile });
      setRelease({ version: "", release_notes: "", force_update: false });
      setReleaseFile(null);
      await load();
      notice("版本发布成功");
    } catch (error) {
      notice(error instanceof Error ? error.message : "版本发布失败");
    } finally {
      setBusy(false);
    }
  }
  const name = (r: Record<string, unknown>) =>
    String(
      r.real_name ||
        r.username ||
        r.config_name ||
        r.attribute_name ||
        r.constant_name ||
        r.rule_code ||
        r.setting_name ||
        r.version ||
        r.setting_key ||
        "-",
    );
  const info = (r: Record<string, unknown>) =>
    String(
      r.model_name ||
        r.provider ||
        r.filename ||
        r.constant_key ||
        r.category_keyword ||
        r.setting_value ||
        r.release_notes ||
        r.description ||
        r.reason ||
        "-",
    );
  const actions = (r: Record<string, unknown>) => (
    <div className="admin-actions">
      <button onClick={() => edit(r)}>编辑</button>
      {[
        "users",
        "models",
        "third",
        "attributes",
        "prompts",
        "restrictions",
      ].includes(tab) && (
        <button onClick={() => void toggle(r)}>
          {Number(r.status) === 1 ? "停用" : "启用"}
        </button>
      )}
      {tab === "users" && (
        <>
          <button onClick={() => void recharge(r)}>充值</button>
          <button onClick={() => void resetPassword(r)}>重置密码</button>
        </>
      )}
      {tab === "models" && (
        <button
          onClick={() => {
            setBusy(true);
            void service
              .testModelConfig(Number(r.id), "请用一句话介绍你自己")
              .then(() => notice("模型测试完成"))
              .catch((error) =>
                notice(error instanceof Error ? error.message : "模型测试失败"),
              )
              .finally(() => setBusy(false));
          }}
        >
          测试
        </button>
      )}
      {tab === "releases" && Number(r.status) !== 1 && (
        <button
          onClick={() =>
            void service
              .publishAppRelease(Number(r.id))
              .then(load)
              .then(() => notice("版本已发布"))
              .catch((error) =>
                notice(error instanceof Error ? error.message : "发布失败"),
              )
          }
        >
          发布
        </button>
      )}
      {[
        "users",
        "models",
        "third",
        "attributes",
        "prompts",
        "restrictions",
        "releases",
      ].includes(tab) && (
        <button className="danger-text" onClick={() => void remove(r)}>
          删除
        </button>
      )}
    </div>
  );
  const fields =
    tab === "users" ? (
      <>
        {field("账号", "username")}
        {field("姓名", "real_name")}
        {field("密码", "password", "password")}
        {field("角色", "role")}
        {field("状态", "status", "number")}
      </>
    ) : tab === "models" ? (
      <>
        {field("配置名称", "config_name")}
        {field("服务商", "provider")}
        {field("模型类型", "model_type")}
        {field("Base URL", "base_url")}
        {field("API Key", "api_key_encrypted", "password")}
        {field("模型名称", "model_name")}
        {field("温度", "temperature", "number")}
        {field("最大输出", "max_tokens", "number")}
        {field("备注", "remark")}
        {field("状态", "status", "number")}
      </>
    ) : tab === "third" ? (
      <>
        {field("配置名称", "config_name")}
        {field("服务类型", "service_type")}
        {field("API Base URL", "api_base_url")}
        {field("Access Key", "access_key_encrypted", "password")}
        {field("Secret Key", "secret_key_encrypted", "password")}
        {field("数据库地址", "db_host")}
        {field("数据库端口", "db_port", "number")}
        {field("数据库名", "db_name")}
        {field("数据库用户", "db_user")}
        {field("数据库密码", "db_password_encrypted", "password")}
        {field("备注", "remark")}
        {field("状态", "status", "number")}
      </>
    ) : tab === "settings" ? (
      <>
        {field("配置键", "setting_key")}
        {field("配置值", "setting_value")}
      </>
    ) : tab === "attributes" ? (
      <>
        {field("属性名称", "attribute_name")}
        {field("属性编码", "attribute_code")}
        {field("属性类型", "attribute_type")}
        {field("说明", "description")}
        {field("默认权重", "default_weight", "number")}
        {field("状态", "status", "number")}
      </>
    ) : tab === "prompts" ? (
      <>
        {field("常量编码", "constant_key")}
        {field("常量名称", "constant_name")}
        {field("常量内容", "constant_content")}
        {field("备注", "remark")}
        {field("状态", "status", "number")}
      </>
    ) : (
      <>
        {field("规则编码", "rule_code")}
        {field("地区", "region")}
        {field("分类关键词", "category_keyword")}
        {field("标题关键词", "title_keyword")}
        {field("动作", "action")}
        {field("原因", "reason")}
        {field("状态", "status", "number")}
      </>
    );
  return (
    <section className="admin-console">
      <div className="admin-console-head">
        <div>
          <h2>系统管理</h2>
          <p>
            账号、模型、第三方接口、选品规则、提示词常量、业务阈值和版本发布统一管理。
          </p>
        </div>
        <button className="secondary" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <div className="admin-tabs">
        {tabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "active" : ""}
            onClick={() => {
              setTab(item.id);
              setForm(null);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "releases" ? (
        <div className="release-upload">
          <div>
            <b>发布新版本</b>
            <span>支持 .exe 或 .zip 安装包</span>
          </div>
          <input
            value={release.version}
            onChange={(e) =>
              setRelease((v) => ({ ...v, version: e.target.value }))
            }
            placeholder="版本号，例如 1.0.3"
          />
          <input
            value={release.release_notes}
            onChange={(e) =>
              setRelease((v) => ({ ...v, release_notes: e.target.value }))
            }
            placeholder="更新说明"
          />
          <input
            type="file"
            accept=".exe,.zip"
            onChange={(e) => setReleaseFile(e.target.files?.[0] || null)}
          />
          <label className="release-check">
            <input
              type="checkbox"
              checked={release.force_update}
              onChange={(e) =>
                setRelease((v) => ({ ...v, force_update: e.target.checked }))
              }
            />{" "}
            强制更新
          </label>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void uploadRelease()}
          >
            上传并发布
          </button>
        </div>
      ) : (
        tab !== "settings" && (
          <button className="primary admin-add" onClick={() => edit()}>
            ＋ 新增{tabs.find((item) => item.id === tab)?.label}
          </button>
        )
      )}
      {form && (
        <div className="admin-editor">
          <div className="admin-editor-head">
            <h3>{form.id ? "编辑记录" : "新增记录"}</h3>
            <button onClick={() => setForm(null)}>×</button>
          </div>
          <div className="admin-form-grid">{fields}</div>
          <div className="admin-editor-actions">
            <button className="secondary" onClick={() => setForm(null)}>
              取消
            </button>
            <button
              className="primary"
              disabled={busy}
              onClick={() => void save()}
            >
              保存
            </button>
          </div>
        </div>
      )}
      <div className="admin-table">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>状态</th>
              <th>信息</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.id || index)}>
                <td>{name(row)}</td>
                <td>
                  {String(
                    row.role ||
                      row.model_type ||
                      row.service_type ||
                      row.attribute_type ||
                      row.action ||
                      row.value_type ||
                      "-",
                  )}
                </td>
                <td>
                  {row.status === 1 || row.status === true
                    ? "启用"
                    : row.status === 0 || row.status === false
                      ? "停用"
                      : "-"}
                </td>
                <td>{info(row)}</td>
                <td>
                  {tab === "settings" ? (
                    <button onClick={() => edit(row)}>编辑</button>
                  ) : (
                    actions(row)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <div className="empty-state">暂无数据</div>}
      </div>
    </section>
  );
}

type ThemeState = {
  font: string;
  size: string;
  background: string;
  opacity: string;
};

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
      return {
        font: "Microsoft YaHei UI",
        size: "14px",
        background: "background.png",
        opacity: "0.30",
        ...JSON.parse(localStorage.getItem("tk_theme") || "{}"),
      };
    } catch {
      return {
        font: "Microsoft YaHei UI",
        size: "14px",
        background: "background.png",
        opacity: "0.30",
      };
    }
  });
  const [dragging, setDragging] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
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
            const scale = Math.min(
              1,
              maxSide / Math.max(image.naturalWidth, image.naturalHeight),
            );
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
            canvas.height = Math.max(
              1,
              Math.round(image.naturalHeight * scale),
            );
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
  return (
    <section className="theme-settings">
      <div className="theme-settings-heading">
        <div>
          <h2>软件换肤</h2>
          <p>调整字体、字号和软件背景，修改会即时生效。</p>
        </div>
        <span className="theme-preview-dot" />
      </div>
      <div className="theme-setting-grid">
        <label>
          字体
          <select
            value={theme.font}
            onChange={(e) => update("font", e.target.value)}
          >
            {themeOptions.fonts.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          字号
          <select
            value={theme.size}
            onChange={(e) => update("size", e.target.value)}
          >
            {themeOptions.sizes.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          背景图
          <select
            value={theme.background}
            onChange={(e) => update("background", e.target.value)}
          >
            {themeOptions.backgrounds.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
            {hasCustomBackground && (
              <option value={theme.background}>自定义背景图</option>
            )}
          </select>
        </label>
      </div>
      <div
        className={dragging ? "theme-upload is-dragging" : "theme-upload"}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (event.currentTarget === event.target) setDragging(false);
        }}
        onDrop={onDrop}
      >
        <Icon name="image" className="theme-upload-icon" />
        <div>
          <b>上传自定义背景图</b>
          <p>点击选择图片，或将图片拖到这里自动换肤</p>
        </div>
        <button
          type="button"
          className="secondary"
          onClick={() => fileInput.current?.click()}
        >
          选择图片
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          hidden
          onChange={(event) => {
            void useBackground(event.target.files?.[0]);
            event.currentTarget.value = "";
          }}
        />
      </div>
      {uploadStatus && <p className="theme-upload-status">{uploadStatus}</p>}
    </section>
  );
}

function AboutPage() {
  return (
    <section className="about-page">
      <div className="about-card">
        <div className="about-mark">TK</div>
        <div>
          <h2>益行跨境 AI 平台</h2>
          <p>TikTok 日本选品专家</p>
          <span>跨境商品分析、AI 选品、供应链匹配与视频内容工作台</span>
        </div>
      </div>
      <div className="about-card about-info">
        <h3>平台信息</h3>
        <div>
          <span>当前客户端</span>
          <b>Electron 桌面版</b>
        </div>
        <div>
          <span>服务范围</span>
          <b>商品选品 · 供应链匹配 · 内容生成</b>
        </div>
        <div>
          <span>数据服务</span>
          <b>多源数据 · 供应链 · 店铺工具</b>
        </div>
      </div>
    </section>
  );
}

function Products2({
  page,
  rows,
  selected,
  onSelect,
  onCollect,
  onSync,
  regions,
  rankRegion,
  rankList,
  rankCategory,
  rankStart,
  rankEnd,
  categories,
  onRankChange,
}: {
  page: Page;
  rows: Product[];
  selected: Product | null;
  onSelect: (p: Product) => void;
  onCollect: (p: Product) => void;
  onSync?: () => void;
  regions: Array<{ region_name?: string; region_code?: string }>;
  rankRegion: string;
  rankList: string;
  rankCategory: string;
  rankStart: string;
  rankEnd: string;
  categories: string[];
  onRankChange: (key: string, value: string) => void;
}) {
  useEffect(() => {
    if (page === "favorites") {
      document
        .querySelectorAll<HTMLButtonElement>(".favorite-list .list-action")
        .forEach((button) => {
          button.textContent = "移除";
        });
      return;
    }
    if (page === "rank") {
      document
        .querySelectorAll<HTMLButtonElement>(".products .product > button")
        .forEach((button, index) => {
          button.textContent = rows[index]?.derived_count
            ? "查看衍生品"
            : "可以衍生";
        });
    }
    if (
      page !== "rank" ||
      JSON.parse(localStorage.getItem("tk_electron_user") || "null")?.role !==
        "admin"
    )
      return;
    const heading = document.querySelector(".products .section-heading");
    if (!heading || heading.querySelector(".rank-sync-button")) return;
    const button = document.createElement("button");
    button.className = "primary rank-sync-button";
    button.textContent = "同步新品榜单";
    button.onclick = async () => {
      button.disabled = true;
      button.textContent = "同步中...";
      try {
        await service.syncConfiguredRanks();
        window.location.reload();
      } catch {
        button.disabled = false;
        button.textContent = "同步新品榜单";
      }
    };
    heading.appendChild(button);
    return () => {
      button.remove();
    };
  }, [page]);
  if (page === "favorites")
    return (
      <section className="favorites-page">
        <div className="section-heading">
          <div>
            <h2>采集箱</h2>
            <p>已保存的商品快照与货源信息</p>
          </div>
        </div>
        <div className="favorite-list">
          <div className="favorite-list-head">
            <span>商品信息</span>
            <span>来源</span>
            <span>国家/地区</span>
            <span>商品分类</span>
            <span>价格</span>
            <span>销量</span>
            <span>货源链接</span>
            <span>操作</span>
          </div>
          {rows.map((item) => (
            <div className="favorite-list-row" key={String(pid(item))}>
              <div className="favorite-product">
                <div className="favorite-thumb">
                  {picture(item) ? (
                    <img src={picture(item)} />
                  ) : (
                    <span>暂无图片</span>
                  )}
                </div>
                <div>
                  <b>{title(item)}</b>
                  <small>{item.source_type || "商品快照"}</small>
                </div>
              </div>
              <span>{String(item.source_type || "-")}</span>
              <span>{String(item.region || "-")}</span>
              <span>{String(item.category || "未分类")}</span>
              <strong>{money(item)}</strong>
              <span>
                {Number(
                  item.sales_count ?? item.supplier_sales_count ?? 0,
                ).toLocaleString()}
              </span>
              {(
                item as Product & { supplier_url?: string; detail_url?: string }
              ).supplier_url ||
              (item as Product & { detail_url?: string }).detail_url ? (
                <a
                  className="supplier-link"
                  href={
                    (
                      item as Product & {
                        supplier_url?: string;
                        detail_url?: string;
                      }
                    ).supplier_url ||
                    (item as Product & { detail_url?: string }).detail_url
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  打开链接
                </a>
              ) : (
                <span className="supplier-link disabled">匹配货源</span>
              )}
              <button className="list-action" onClick={() => onCollect(item)}>
                查看详情
              </button>
            </div>
          ))}
          {!rows.length && <div className="empty-state">暂无采集商品</div>}
        </div>
      </section>
    );
  const regionLabel =
    regions.find((item) => item.region_code === rankRegion)?.region_name ||
    rankRegion;
  return (
    <div className="workspace">
      <section className="products">
        <div className="rank-filters">
          <div className="rank-filter-line">
            <b>上架时间</b>
            <input
              type="date"
              value={rankStart}
              onChange={(e) => onRankChange("start", e.target.value)}
            />
            <span>至</span>
            <input
              type="date"
              value={rankEnd}
              onChange={(e) => onRankChange("end", e.target.value)}
            />
          </div>
          <div className="rank-filter-line">
            <b>国家/地区</b>
            <button
              className={rankRegion === "ALL" ? "active" : ""}
              onClick={() => onRankChange("region", "ALL")}
            >
              全部
            </button>
            {regions.map((item) => (
              <button
                key={item.region_code}
                className={rankRegion === item.region_code ? "active" : ""}
                onClick={() =>
                  onRankChange("region", String(item.region_code || ""))
                }
              >
                {item.region_name || item.region_code}
              </button>
            ))}
          </div>
          <div className="rank-filter-line">
            <b>商品分类</b>
            <button
              className={!rankCategory ? "active" : ""}
              onClick={() => onRankChange("category", "")}
            >
              全部
            </button>
            {categories.map((item) => (
              <button
                key={item}
                className={rankCategory === item ? "active" : ""}
                onClick={() => onRankChange("category", item)}
              >
                {item}
              </button>
            ))}
          </div>
          <div className="rank-filter-line">
            <b>商品榜单</b>
            {[
              { value: "sales", label: "销量榜" },
              { value: "new", label: "新品榜" },
              { value: "hot", label: "热销榜" },
            ].map((item) => (
              <button
                key={item.value}
                className={rankList === item.value ? "active" : ""}
                onClick={() => onRankChange("list", item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="section-heading">
          <div>
            <h2>
              {rankList === "sales"
                ? "销量榜"
                : rankList === "hot"
                  ? "热销榜"
                  : "新品榜单"}
            </h2>
            <p>
              {regionLabel} · {rows.length} 个商品
            </p>
          </div>
        </div>
        <div className="product-grid">
          {rows.map((p) => (
            <article
              className={
                selected && pid(selected) === pid(p)
                  ? "product selected"
                  : "product"
              }
              key={String(pid(p))}
              onClick={() => onSelect(p)}
            >
              <div className="image-wrap">
                {picture(p) ? (
                  <img src={picture(p)} loading="lazy" />
                ) : (
                  <div className="image-empty">暂无图片</div>
                )}
              </div>
              <h3>{title(p)}</h3>
              <div className="product-tag">
                {p.category || p.source_type || "商品"}
              </div>
              <div className="product-meta">
                <strong>{money(p)}</strong>
                <span>
                  销量{" "}
                  {Number(
                    p.sales_count ?? p.supplier_sales_count ?? 0,
                  ).toLocaleString()}
                </span>
              </div>
              <button
                className="primary"
                onClick={(e) => {
                  e.stopPropagation();
                  onCollect(p);
                }}
              >
                加入采集箱
              </button>
            </article>
          ))}
        </div>
        {!rows.length && <div className="empty-state">暂无数据</div>}
      </section>
      <aside className="report">
        <h2>选品分析报告</h2>
        {selected ? (
          <>
            <div className="report-product">
              {picture(selected) ? (
                <img src={picture(selected)} />
              ) : (
                <div className="image-empty">暂无图片</div>
              )}
              <div>
                <h3>{title(selected)}</h3>
                <strong>{money(selected)}</strong>
                <p>
                  销量{" "}
                  {Number(
                    selected.sales_count ?? selected.supplier_sales_count ?? 0,
                  ).toLocaleString()}
                </p>
                <p>
                  AI 参考分{" "}
                  {Number(
                    selected.ai_score ?? selected.weighted_score ?? 0,
                  ).toFixed(1)}
                </p>
              </div>
            </div>
            <button
              className="primary full"
              onClick={() => onCollect(selected)}
            >
              加入采集箱
            </button>
          </>
        ) : (
          <div className="empty-state">请选择商品</div>
        )}
      </aside>
    </div>
  );
}

function Products3Content({
  page,
  rows,
  selected,
  onSelect,
  onDerive,
  onAddLibrary,
  onPublish,
  regions,
}: {
  page: "rank" | "favorites";
  rows: Product[];
  selected: Product | null;
  onSelect: (p: Product) => void;
  onDerive: (p: Product) => void;
  onAddLibrary: (p: Product) => Promise<void>;
  onPublish: (p: Product) => void;
  regions: Array<{ region_name?: string; region_code?: string }>;
}) {
  const [detail, setDetail] = useState<Product | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const lookupRegionName = (value?: string) =>
    FIXED_COUNTRIES.find(
      (item) => item.code === String(value || "").toUpperCase(),
    )?.name || value || "未标注";
  const regionLabel = lookupRegionName;
  const maxSales = Math.max(
    1,
    ...rows.map((r) =>
      Number(r.sales_count ?? r.supplier_sales_count ?? 0),
    ),
  );
  if (page === "favorites")
    return (
      <section className="favorites-page">
        <div className="section-heading">
          <div>
            <h2>采集箱</h2>
            <p>已保存的商品快照与货源信息</p>
          </div>
        </div>
        <div className="favorite-list">
          <div className="favorite-list-head">
            <span>商品信息</span>
            <span>来源</span>
            <span>国家</span>
            <span>商品分类</span>
            <span>价格</span>
            <span>销量</span>
            <span>货源链接</span>
            <span>操作</span>
          </div>
          {rows.map((item) => {
            const url = supplierUrl(item);
            return (
              <div className="favorite-list-row" key={String(pid(item))}>
                <div className="favorite-product">
                  <div className="favorite-thumb">
                    {picture(item) ? (
                      <img src={picture(item)} />
                    ) : (
                      <span>暂无图片</span>
                    )}
                  </div>
                  <div>
                    <b>{title(item)}</b>
                    <small>{productSourceLabel(item)}</small>
                  </div>
                </div>
                <span>{productSourceLabel(item)}</span>
                <span>{regionLabel(item.region)}</span>
                <span>{categoryLabel(item.category)}</span>
                <strong>{money(item)}</strong>
                <span>
                  {Number(
                    item.sales_count ?? item.supplier_sales_count ?? 0,
                  ).toLocaleString()}
                </span>
                {url ? (
                  <a
                    className="supplier-link"
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开链接
                  </a>
                ) : (
                  <span className="supplier-link disabled">待匹配</span>
                )}
                <div className="favorite-actions">
                  <button
                    className="list-action"
                    onClick={() => onPublish(item)}
                  >
                    加入上品
                  </button>
                  <button
                    className="list-action secondary-action"
                    onClick={() => setDetail(item)}
                  >
                    查看详情
                  </button>
                </div>
              </div>
            );
          })}
          {!rows.length && <div className="empty-state">暂无采集商品</div>}
        </div>
        {detail && (
          <div
            className="collection-detail-backdrop"
            onClick={() => setDetail(null)}
          >
            <section
              className="collection-detail"
              onClick={(event) => event.stopPropagation()}
            >
              <button className="modal-close" onClick={() => setDetail(null)}>
                ×
              </button>
              <div className="collection-detail-head">
                {picture(detail) ? (
                  <img src={picture(detail)} />
                ) : (
                  <div className="image-empty">暂无图片</div>
                )}
                <div>
                  <h2>{title(detail)}</h2>
                  <strong>{money(detail)}</strong>
                  <p>
                    来源：{productSourceLabel(detail)} ·{" "}
                    {regionLabel(detail.region)}
                  </p>
                  <p>
                    分类：{categoryLabel(detail.category)} · 销量：
                    {Number(
                      detail.sales_count ?? detail.supplier_sales_count ?? 0,
                    ).toLocaleString()}
                  </p>
                </div>
              </div>
              <h3>商品说明</h3>
              <p>{detail.recommendation_reason || "暂无商品说明"}</p>
              <button className="primary" onClick={() => onPublish(detail)}>
                加入上品
              </button>
            </section>
          </div>
        )}
      </section>
    );
  const regionName = regionLabel(String(selected?.region || "JP"));
  return (
    <div className="rank-workspace">
      <section className="products">
        <div className="section-heading">
          <div>
            <h2>新品榜单</h2>
            <p>
              {regionName} · {rows.length} 个商品
            </p>
          </div>
        </div>
        <div className="product-grid">
          {rows.map((p, index) => {
            const key = String(pid(p));
            const hasDerived = Number(p.derived_count || 0) > 0;
            const rank = index + 1;
            const sales = Number(p.sales_count ?? p.supplier_sales_count ?? 0);
            const heat = Math.max(6, Math.round((sales / maxSales) * 100));
            return (
              <article
                className={
                  selected && pid(selected) === pid(p)
                    ? "product selected"
                    : "product"
                }
                key={key}
                onClick={() => onSelect(p)}
              >
                <div className="image-wrap">
                  {picture(p) ? (
                    <img src={picture(p)} loading="lazy" />
                  ) : (
                    <div className="image-empty">暂无图片</div>
                  )}
                  <span className={`card-index${rank <= 3 ? ` top${rank === 1 ? "" : rank}` : ""}`}>{rank}</span>
                </div>
                <h3>{title(p)}</h3>
                <div className="card-tags">
                  <span className="card-chip">{productSourceLabel(p)}</span>
                  {supplierUrl(p) ? (
                    <span className="supply-badge ok">有货源</span>
                  ) : (
                    <span className="supply-badge no">无货源</span>
                  )}
                </div>
                <div className="product-meta">
                  <strong>{money(p)}</strong>
                  <span>
                    销量{" "}
                    {sales.toLocaleString()}
                  </span>
                </div>
                <div className="rank-heat">
                  <div className="rank-heat-track">
                    <div className="rank-heat-fill" style={{ width: `${heat}%` }} />
                  </div>
                  <div className="rank-heat-label">
                    <span>热度</span>
                    <span>销量 {sales.toLocaleString()}</span>
                  </div>
                </div>
                <div className="product-actions">
                  <button
                    className="primary"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDerive(p);
                    }}
                  >
                    {hasDerived ? "查看衍生品" : "可以衍生"}
                  </button>
                  <button
                    className="secondary"
                    disabled={added[key]}
                    onClick={async (event) => {
                      event.stopPropagation();
                      await onAddLibrary(p);
                      setAdded((current) => ({ ...current, [key]: true }));
                    }}
                  >
                    {added[key] ? "已加入选品库" : "加入选品库"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
        {!rows.length && <div className="empty-state">暂无新品榜单数据</div>}
      </section>
    </div>
  );
}

function DerivationPipelineModal({
  source,
  progress,
  stage,
  status,
  message,
  counters,
  groups,
  reportData,
  onClose,
  onStart,
}: {
  source: Product;
  progress: number;
  stage: string;
  status: "idle" | "running" | "success" | "failed";
  message: string;
  counters: Record<string, number>;
  groups: Array<{
    keyword_id: number;
    keyword: string;
    items: Array<Record<string, unknown>>;
  }>;
  reportData: PipelineReportData | null;
  onClose: () => void;
  onStart: () => void;
}) {
  const nodes = [
    "AI 生成衍生方向",
    "匹配优质供应链",
    "拓展市场在售样本",
    "日本法规风控",
    "蓝海竞争过滤",
    "生成可视化报告",
    "精选最终 10 款",
  ];
  const stepMap: Record<string, number> = {
    created: 0,
    keyword_generation: 0,
    supplier_search: 1,
    price_seed_selection: 1,
    image_search: 2,
    product_detail: 2,
    compliance_filter: 3,
    blue_ocean_filter: 4,
    report_generation: 5,
    final_selection: 6,
  };
  const currentStep = stepMap[stage] ?? Math.min(6, Math.floor(progress / 15));
  const [logs, setLogs] = useState<
    Array<{ time: string; step: number; message: string }>
  >([]);
  const [reportOpen, setReportOpen] = useState(false);
  const displayedStageRef = useRef("");
  const displayedStageAtRef = useRef(0);

  useEffect(() => {
    if (status === "idle") {
      setLogs([]);
      displayedStageRef.current = "";
      return;
    }
    const elapsed = Date.now() - displayedStageAtRef.current;
    if (
      displayedStageRef.current &&
      stage !== displayedStageRef.current &&
      elapsed < 1000
    ) {
      const timer = window.setTimeout(() => {
        displayedStageRef.current = stage;
        displayedStageAtRef.current = Date.now();
        const time = new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        setLogs((prev) =>
          [...prev, { time, step: currentStep, message: message || nodes[currentStep] || "任务推进中" }].slice(-6),
        );
      }, 1000 - elapsed);
      return () => window.clearTimeout(timer);
    }
    if (stage !== displayedStageRef.current) {
      displayedStageRef.current = stage;
      displayedStageAtRef.current = Date.now();
      const time = new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setLogs((prev) =>
        [...prev, { time, step: currentStep, message: message || nodes[currentStep] || "任务推进中" }].slice(-6),
      );
    }
  }, [stage, status, message, currentStep]);

  return (
    <div
      className="modal-backdrop"
      onClick={status === "running" ? undefined : onClose}
    >
      <section
        className="modal derived-pipeline-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="derived-pipeline-head">
          <div className="head-main">
            {picture(source) ? (
              <img src={picture(source)} loading="lazy" />
            ) : (
              <div className="image-empty" style={{ width: 52, height: 52, borderRadius: 10, display: "grid", placeItems: "center", fontSize: 11 }}>暂无图片</div>
            )}
            <div className="head-text">
              <h2>衍生品智能任务</h2>
              <p title={title(source)}>原商品：{title(source)}</p>
            </div>
          </div>
          <div className="derived-pipeline-actions">
            <button
              className="primary"
              onClick={onStart}
              disabled={status === "running" || status === "success"}
            >
              {status === "idle"
                ? "开始衍生"
                : status === "running"
                  ? "衍生执行中..."
                  : status === "success"
                    ? "已完成"
                    : "重新开始"}
            </button>
            <button
              className="modal-close"
              onClick={onClose}
              disabled={status === "running"}
            >
              ×
            </button>
          </div>
        </div>
        <div className="derived-pipeline-progress">
          <div>
            <span>{message || "确认后开始衍生任务"}</span>
            <b>{progress}%</b>
          </div>
          <i>
            <em style={{ transform: `scaleX(${progress / 100})` }} />
          </i>
        </div>
        <div className="derived-pipeline-layout">
          <div className="derived-pipeline-steps">
            <div className="derived-panel-title">
              <h3>任务执行流程</h3>
              <span className={`flow-status ${status}`}>
                {status === "idle"
                  ? "待开始"
                  : status === "success"
                    ? "已完成"
                    : status === "failed"
                      ? "失败"
                      : "执行中"}
              </span>
            </div>
            <div className="selection-flow-row">
              {nodes.map((node, index) => (
                <div
                  key={node}
                  className={`flow-node ${index < currentStep || status === "success" ? "done" : index === currentStep && status === "running" ? "active running" : ""}`}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <b>{node}</b>
                    <small>
                      {status === "idle"
                        ? "待开始"
                        : index === currentStep
                          ? message || "处理中"
                          : index < currentStep || status === "success"
                            ? "该步骤已完成"
                            : "等待执行"}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="derived-pipeline-board">
            <div className="task-board-header">
              <h2>任务结果看板</h2>
              <div className="task-board-header-actions">
                {status === "success" && reportData && (
                  <button
                    className="primary small"
                    onClick={() => setReportOpen(true)}
                  >
                    查看完整市场机会报告
                  </button>
                )}
                <span className="task-board-auto-hint">
                  {status === "success"
                    ? "已自动加入选品库"
                    : status === "running"
                      ? "AI 分析中…"
                      : "等待开始"}
                </span>
              </div>
            </div>
            <div className="task-board-logs">
              <h4>实时动态</h4>
              {logs.length ? (
                logs.slice(-3).map((log, idx) => (
                  <div
                    key={`${log.time}-${idx}`}
                    className={`task-board-log ${idx === logs.length - 1 && status === "running" ? "current" : ""}`}
                  >
                    <i />
                    <time>{log.time}</time>
                    <span>{log.message}</span>
                  </div>
                ))
              ) : (
                <div className="task-board-log">
                  <i />
                  <span>等待任务开始…</span>
                </div>
              )}
            </div>
            <div className="task-board-body">
              <DerivationStage
                status={status}
                currentStep={currentStep}
                reportData={reportData}
                counters={counters}
                groups={groups}
              />
            </div>
          </div>
        </div>
        {reportOpen && reportData && (
          <SelectionReport
            data={reportData}
            onClose={() => setReportOpen(false)}
          />
        )}
      </section>
    </div>
  );
}

function useDerivation() {
  const [derivedSource, setDerivedSource] = useState<Product | null>(null);
  const [derivedRows, setDerivedRows] = useState<Product[]>([]);
  const [derivedLoading, setDerivedLoading] = useState(false);
  const [error, setError] = useState("");
  const [derivedReady, setDerivedReady] = useState<Record<string, boolean>>({});
  const [derivedAdded, setDerivedAdded] = useState<Record<string, boolean>>({});
  const [pipelineActive, setPipelineActive] = useState(false);
  const [pipelineTaskId, setPipelineTaskId] = useState<number | null>(null);
  const [pipelineProgress, setPipelineProgress] = useState(0);
  const [pipelineStage, setPipelineStage] = useState("created");
  const [pipelineStatus, setPipelineStatus] = useState<
    "idle" | "running" | "success" | "failed"
  >("idle");
  const [pipelineMessage, setPipelineMessage] = useState("");
  const [pipelineCounters, setPipelineCounters] = useState<
    Record<string, number>
  >({});
  const [pipelineGroups, setPipelineGroups] = useState<
    Array<{
      keyword_id: number;
      keyword: string;
      items: Array<Record<string, unknown>>;
    }>
  >([]);
  const [pipelineReportData, setPipelineReportData] =
    useState<PipelineReportData | null>(null);

  async function viewDerived(product: Product) {
    setDerivedLoading(true);
    setError("");
    setDerivedSource(product);
    setDerivedRows([]);
    try {
      const items = await service.getDerivedProducts(pid(product));
      setDerivedRows(items);
      setDerivedReady((current) => ({
        ...current,
        [String(pid(product))]: true,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取衍生品失败");
    } finally {
      setDerivedLoading(false);
    }
  }
  function generateDerived(product: Product) {
    setPipelineActive(true);
    setDerivedSource(product);
    setPipelineStatus("idle");
    setPipelineProgress(0);
    setPipelineStage("created");
    setPipelineMessage("请确认后点击“开始衍生”");
    setPipelineCounters({});
    setPipelineGroups([]);
    setPipelineReportData(null);
  }
  async function startDerived() {
    if (!derivedSource || pipelineStatus === "running") return;
    setPipelineStatus("running");
    setPipelineProgress(1);
    setPipelineStage("created");
    setPipelineMessage("正在创建衍生任务");
    try {
      const result = await service.createSelectionPipelineTask(
        title(derivedSource),
        { mode: "derivation", source_product_id: Number(pid(derivedSource)) },
      );
      if (!result.task_id) throw new Error("服务未返回衍生任务编号");
      setPipelineTaskId(Number(result.task_id));
    } catch (e) {
      setPipelineStatus("failed");
      setPipelineMessage(e instanceof Error ? e.message : "启动衍生任务失败");
    }
  }
  function closeDerived() {
    setPipelineTaskId(null);
    setPipelineActive(false);
    setDerivedSource(null);
  }

  useEffect(() => {
    if (!pipelineTaskId) return;
    const timer = window.setInterval(async () => {
      try {
        const data = await service.getSelectionPipelineTask(pipelineTaskId);
        setPipelineProgress(Number(data.progress || 0));
        setPipelineStage(String(data.stage || "created"));
        setPipelineMessage(String(data.message || ""));
        setPipelineCounters(data.counters || {});
        if (Array.isArray(data.board_groups))
          setPipelineGroups(data.board_groups);
        setPipelineReportData(data as PipelineReportData);
        if (data.status === "success" || data.status === "failed") {
          window.clearInterval(timer);
          setPipelineStatus(data.status);
          setPipelineTaskId(null);
          if (data.status === "success" && derivedSource)
            setDerivedReady((current) => ({
              ...current,
              [String(pid(derivedSource))]: true,
            }));
        }
      } catch (e) {
        window.clearInterval(timer);
        setPipelineTaskId(null);
        setPipelineStatus("failed");
        setPipelineMessage(e instanceof Error ? e.message : "衍生任务查询失败");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [pipelineTaskId]);
  useEffect(() => {
    if (!pipelineActive) return;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    const previousBodyOverflow = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousBodyOverflow;
    };
  }, [pipelineActive]);

  return {
    derivedSource,
    setDerivedSource,
    derivedRows,
    derivedLoading,
    error,
    derivedReady,
    derivedAdded,
    setDerivedAdded,
    pipelineActive,
    pipelineProgress,
    pipelineStage,
    pipelineStatus,
    pipelineMessage,
    pipelineCounters,
    pipelineGroups,
    pipelineReportData,
    viewDerived,
    generateDerived,
    startDerived,
    closeDerived,
  };
}

function Products3ContentFixed({
  rows,
  selected,
  onSelect,
  onDerive,
  onAddLibrary,
  regions,
}: {
  rows: Product[];
  selected: Product | null;
  onSelect: (p: Product) => void;
  onDerive: (p: Product) => void;
  onAddLibrary: (p: Product) => Promise<void>;
  regions: Array<{ region_name?: string; region_code?: string }>;
}) {
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const {
    derivedSource,
    setDerivedSource,
    derivedRows,
    derivedLoading,
    error,
    derivedReady,
    derivedAdded,
    setDerivedAdded,
    pipelineActive,
    pipelineProgress,
    pipelineStage,
    pipelineStatus,
    pipelineMessage,
    pipelineCounters,
    pipelineGroups,
    pipelineReportData,
    viewDerived,
    generateDerived,
    startDerived,
    closeDerived,
  } = useDerivation();
  const regionName =
    FIXED_COUNTRIES.find(
      (item) => item.code === String(selected?.region || "").toUpperCase(),
    )?.name || selected?.region || "未标注";
  const maxSales = Math.max(
    1,
    ...rows.map((r) =>
      Number(r.sales_count ?? r.supplier_sales_count ?? 0),
    ),
  );
  return (
    <>
      <div className="rank-workspace">
        <section className="products">
          <div className="section-heading">
            <div>
              <h2>新品榜单</h2>
              <p>
                {regionName} · {rows.length} 个商品
              </p>
            </div>
          </div>
          <div className="product-grid">
            {rows.map((p, index) => {
              const key = String(pid(p));
              const hasDerived =
                derivedReady[key] ?? Number(p.derived_count || 0) > 0;
              const rank = index + 1;
              const sales = Number(p.sales_count ?? p.supplier_sales_count ?? 0);
              const heat = Math.max(6, Math.round((sales / maxSales) * 100));
              return (
                <article
                  className={
                    selected && pid(selected) === pid(p)
                      ? "product selected"
                      : "product"
                  }
                  key={key}
                  onClick={() => onSelect(p)}
                >
                  <div className="image-wrap">
                    {picture(p) ? (
                      <img src={picture(p)} loading="lazy" />
                    ) : (
                      <div className="image-empty">暂无图片</div>
                    )}
                  </div>
                  <h3>{title(p)}</h3>
                  <div className="product-meta">
                    <strong>{money(p)}</strong>
                    <span>
                      销量{" "}
                      {Number(
                        p.sales_count ?? p.supplier_sales_count ?? 0,
                      ).toLocaleString()}
                    </span>
                  </div>
                  <div className="product-actions">
                    <button
                      className="primary"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (hasDerived) void viewDerived(p);
                        else void generateDerived(p);
                      }}
                    >
                      {hasDerived ? "查看衍生品" : "可以衍生"}
                    </button>
                    <button
                      className="secondary"
                      disabled={added[key]}
                      onClick={async (event) => {
                        event.stopPropagation();
                        await onAddLibrary(p);
                        setAdded((current) => ({ ...current, [key]: true }));
                      }}
                    >
                      {added[key] ? "已加入选品库" : "加入选品库"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
          {!rows.length && <div className="empty-state">暂无新品榜单数据</div>}
        </section>
      </div>
      {derivedSource && !pipelineActive && (
        <div className="modal-backdrop" onClick={() => setDerivedSource(null)}>
          <section
            className="modal derived-products-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="derived-modal-close"
              onClick={() => setDerivedSource(null)}
            >
              ×
            </button>
            <div className="derived-modal-head">
              {picture(derivedSource) ? (
                <img src={picture(derivedSource)} loading="lazy" />
              ) : (
                <div className="derived-modal-image image-empty" style={{ width: 52, height: 52, borderRadius: 10 }}>暂无图片</div>
              )}
              <div className="head-text">
                <span className="source-tag">原商品</span>
                <h2>查看衍生品</h2>
                <p className="source-title" title={title(derivedSource)}>
                  {title(derivedSource)}
                </p>
              </div>
            </div>
            <div className="derived-modal-body">
              {derivedLoading ? (
                <div className="derived-empty">
                  <span className="empty-icon">⟳</span>
                  <b>正在读取衍生品</b>
                  <span>请稍候，正在加载关联商品数据</span>
                </div>
              ) : error ? (
                <div className="derived-empty">
                  <span className="empty-icon">!</span>
                  <b>读取失败</b>
                  <span>{error}</span>
                </div>
              ) : !derivedRows.length ? (
                <div className="derived-empty">
                  <span className="empty-icon">✦</span>
                  <b>暂无衍生品</b>
                  <span>该商品尚未生成衍生方向，可点击「可以衍生」智能生成</span>
                </div>
              ) : (
                <div className="derived-modal-grid">
                  {derivedRows.map((item, index) => {
                    const itemKey = String(pid(item));
                    const sales = Number(
                      item.sales_count ?? item.supplier_sales_count ?? 0,
                    );
                    const maxSales = Math.max(
                      1,
                      ...derivedRows.map((r) =>
                        Number(r.sales_count ?? r.supplier_sales_count ?? 0),
                      ),
                    );
                    const heat = Math.round((sales / maxSales) * 100);
                    return (
                      <article className="derived-modal-card" key={itemKey}>
                        <span className="derived-rank">{index + 1}</span>
                        <div className="derived-modal-image">
                          {picture(item) ? (
                            <img src={picture(item)} loading="lazy" />
                          ) : (
                            <div className="image-empty">暂无图片</div>
                          )}
                        </div>
                        <div className="derived-card-body">
                          <h3 title={title(item)}>{title(item)}</h3>
                          <div className="derived-meta">
                            <strong>{money(item)}</strong>
                            <span>销量 {sales.toLocaleString()}</span>
                          </div>
                          <div className="derived-heat">
                            <i><em style={{ width: `${heat}%` }} /></i>
                            <span>热度 {heat}%</span>
                          </div>
                          <button
                            className="derived-library-button"
                            disabled={derivedAdded[itemKey]}
                            onClick={async () => {
                              await onAddLibrary(item);
                              setDerivedAdded((current) => ({
                                ...current,
                                [itemKey]: true,
                              }));
                            }}
                          >
                            {derivedAdded[itemKey] ? "已加入选品库" : "加入选品库"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </div>
      )}
      {derivedSource && pipelineActive && (
        <DerivationPipelineModal
          source={derivedSource}
          progress={pipelineProgress}
          stage={pipelineStage}
          status={pipelineStatus}
          message={pipelineMessage}
          counters={pipelineCounters}
          groups={pipelineGroups}
          reportData={pipelineReportData}
          onStart={startDerived}
          onClose={closeDerived}
        />
      )}
    </>
  );
}

function Products3({
  page,
  rows,
  selected,
  onSelect,
  onDerive,
  onAddLibrary,
  onPublish,
  regions,
}: {
  page: "rank" | "favorites";
  rows: Product[];
  selected: Product | null;
  onSelect: (p: Product) => void;
  onDerive: (p: Product) => void;
  onAddLibrary: (p: Product) => Promise<void>;
  onPublish: (p: Product) => void;
  regions: Array<{ region_name?: string; region_code?: string }>;
}) {
  const [region, setRegion] = useState("ALL");
  const [category, setCategory] = useState("ALL");
  const [regionExpand, setRegionExpand] = useState(false);
  const [categoryExpand, setCategoryExpand] = useState(false);
  if (page === "favorites")
    return (
      <Products3Content
        page={page}
        rows={rows}
        selected={selected}
        onSelect={onSelect}
        onDerive={onDerive}
        onAddLibrary={onAddLibrary}
        onPublish={onPublish}
        regions={regions}
      />
    );
  const categoryOptions = FIXED_CATEGORIES;
  const filtered = rows.filter(
    (item) =>
      (region === "ALL" ||
        String(item.region || "").toUpperCase() === region) &&
      (category === "ALL" || categoryLabel(item.category) === category),
  );
  return (
    <section className="rank-page">
      <div className="rank-page-heading">
        <div>
          <h2>新品榜单</h2>
          <p>按国家/地区和商品分类筛选新品</p>
        </div>
        <span>{filtered.length} 个商品</span>
      </div>
      <div className="rank-page-filters tiktok-filters">
        <RegionFilterRow
          value={region}
          onChange={setRegion}
          expanded={regionExpand}
          onToggleExpand={() => setRegionExpand((v) => !v)}
        />
        <CategoryFilterRow
          options={categoryOptions}
          value={category}
          onChange={setCategory}
          expanded={categoryExpand}
          onToggleExpand={() => setCategoryExpand((v) => !v)}
          allValue="ALL"
        />
      </div>
      <Products3ContentFixed
        rows={filtered}
        selected={selected}
        onSelect={onSelect}
        onDerive={onDerive}
        onAddLibrary={onAddLibrary}
        regions={regions}
      />
    </section>
  );
}

function App2Clean() {
  const stored = localStorage.getItem("tk_electron_user");
  const [user, setUser] = useState<User | null>(() => {
    if (!stored) return null;
    const parsed = JSON.parse(stored) as User;
    return { ...parsed, credits: parsed.credits ?? parsed.credit_balance ?? 0 };
  });
  const [page, setPage] = useState<Page>("studio");
  const [rows, setRows] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [regions, setRegions] = useState<
    Array<{ region_name?: string; region_code?: string }>
  >([]);
  const [rankRegion, setRankRegion] = useState("ALL");
  const [rankList, setRankList] = useState("new");
  const [rankCategory, setRankCategory] = useState("");
  const [rankStart, setRankStart] = useState("");
  const [rankEnd, setRankEnd] = useState("");
  const [notice, setNotice] = useState("");
  const allowed = useMemo(
    () => menus.filter((m) => m.roles.includes(user?.role || "student")),
    [user],
  );
  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 3000);
  };
  const load = async (next: Page) => {
    if (!["library", "rank"].includes(next)) return;
    try {
      const data =
        next === "library"
          ? await service.getLibrary()
          : next === "favorites"
            ? await service.getFavorites()
            : await service.getRanks({
                region: rankRegion === "ALL" ? "JP" : rankRegion,
                list_type: rankList,
                category: rankCategory,
                start_date: rankStart,
                end_date: rankEnd,
                page: 1,
                pagesize: 50,
                paged: true,
              });
      const list = Array.isArray(data)
        ? data
        : (data as { items?: Product[] })?.items || [];
      const normalized = list.map((item) => ({
        ...item,
        region: String(item.region || "").toUpperCase(),
        category: categoryLabel(item.category),
      }));
      setRows(normalized);
      setSelected(normalized[0] || null);
    } catch (e) {
      flash(e instanceof Error ? e.message : "读取数据失败");
    }
  };
  useEffect(() => {
    if (user) {
      service
        .getRegions()
        .then(setRegions)
        .catch(() => setRegions([]));
    }
  }, [user]);
  useEffect(() => {
    if (user) load(page);
  }, [user, page, rankRegion, rankList, rankCategory, rankStart, rankEnd]);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("tk_theme") || "{}");
      applyTheme({
        font: "Microsoft YaHei UI",
        size: "14px",
        background: "background.png",
        opacity: "0.30",
        ...saved,
      });
    } catch {
      applyTheme({
        font: "Microsoft YaHei UI",
        size: "14px",
        background: "background.png",
        opacity: "0.30",
      });
    }
  }, []);
  if (!user)
    return (
      <>
        <WindowTitlebar />
        <Login done={setUser} />
      </>
    );
  const collect = async (product: Product) => {
    try {
      if (page === "favorites" && product.id) {
        await service.removeFavorite(product.id);
        await load("favorites");
        flash("已从采集箱移除");
      } else if (page === "rank" && product.id) {
        await service.generateDerived(product.id);
        flash("已开始生成衍生品");
      } else {
        await service.collect(product);
        flash("已加入采集箱");
      }
    } catch (e) {
      flash(e instanceof Error ? e.message : "操作失败");
    }
  };
  const addToLibrary = async (product: Product) => {
    try {
      await service.addLibraryProduct(product);
      flash("商品已加入选品库");
    } catch (e) {
      flash(e instanceof Error ? e.message : "加入选品库失败");
      throw e;
    }
  };
  const publishProduct = (product: Product) => {
    const url = supplierUrl(product);
    if (!url) {
      flash("该商品没有可用的货源链接");
      return;
    }
    localStorage.setItem("tk_publish_prefill_url", url);
    setPage("store");
    flash("已将商品链接带入店铺管理");
  };
  const categories = FIXED_CATEGORIES;
  const onRankChange = (key: string, value: string) => {
    if (key === "region") setRankRegion(value);
    if (key === "list") setRankList(value);
    if (key === "category") setRankCategory(value);
    if (key === "start") setRankStart(value);
    if (key === "end") setRankEnd(value);
  };
  return (
    <>
      <WindowTitlebar />
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">TK</div>
            <div className="brand-text">
              <b>益行跨境 AI 平台</b>
              <span>TikTok 日本选品专家</span>
            </div>
          </div>
          <nav>
            {Object.entries(
              allowed.reduce<Record<string, typeof allowed>>((acc, item) => {
                (acc[item.group] = acc[item.group] || []).push(item);
                return acc;
              }, {}),
            ).map(([group, items]) => (
              <div className="nav-group" key={group}>
                <span className="nav-group-title">{group}</span>
                {items.map((item) => (
                  <button
                    key={item.id}
                    className={page === item.id ? "active" : ""}
                    onClick={() => setPage(item.id)}
                  >
                    <Icon name={item.icon} />
                    <span className="nav-label">{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>
          <div className="account">
            <div className="avatar">
              {(user.real_name || user.username || "A").slice(0, 1)}
            </div>
            <div className="account-copy">
              <b>{user.real_name || user.username}</b>
              <span>
                {user.role} · 积分 {user.credits ?? user.credit_balance ?? 0}
              </span>
            </div>
            <button
              className="logout"
              onClick={() => {
                service.logout();
                setUser(null);
              }}
            >
              <span className="logout-label">退出登录</span>
            </button>
          </div>
        </aside>
        <main className="main">
          {page === "studio" && (
            <SmartSelection
              user={user}
              onNotice={flash}
            />
          )}
          {page === "library" && (
            <LibraryPage rows={rows} onPublish={publishProduct} onAddLibrary={addToLibrary} />
          )}
          {["rank", "favorites"].includes(page) && (
            <Products3
              page={page as "rank" | "favorites"}
              rows={rows}
              selected={selected}
              onSelect={setSelected}
              onDerive={collect}
              onAddLibrary={addToLibrary}
              onPublish={publishProduct}
              regions={regions}
            />
          )}
          {page === "dashboard" && <Dashboard />}
          {page === "store" && (
            <StorePage
              user={user}
              notice={flash}
              onCreditChange={(credits) =>
                setUser((current) =>
                  current ? { ...current, credits } : current,
                )
              }
            />
          )}
          {page === "video" && (
            <VideoPage
              user={user}
              notice={flash}
              onCreditChange={(credits) =>
                setUser((current) =>
                  current ? { ...current, credits } : current,
                )
              }
            />
          )}
          {page === "profile" && (
            <>
              <Profile
                user={user}
                onNotice={flash}
                onCreditChange={(credits) =>
                  setUser((current) =>
                    current ? { ...current, credits } : current,
                  )
                }
              />
              <ThemeSettings />
            </>
          )}
          {page === "teacher" && <Teacher notice={flash} />}
          {page === "about" && <AboutPage />}
          {page === "admin" && <AdminConsole notice={flash} />}
          {notice && <div className="toast">{notice}</div>}
        </main>
      </div>
    </>
  );
}

export default App2Clean;
