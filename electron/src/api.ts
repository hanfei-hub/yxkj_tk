import axios from "axios";
import type { ConfigItem, Product, User, VideoProject } from "./types";

const defaultBase = "http://120.26.207.89:8002";
localStorage.setItem("tk_api_base", defaultBase);
const baseURL = defaultBase;
export const api = axios.create({ baseURL, timeout: 180000 });

export function setToken(token: string | null) {
  if (token) localStorage.setItem("tk_electron_token", token);
  else localStorage.removeItem("tk_electron_token");
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("tk_electron_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 404) {
      const cfg = err.config || {};
      const method = String(cfg.method || "GET").toUpperCase();
      const url = cfg.url || "";
      err.message = `接口未找到 [404]: ${method} ${url}`;
    }
    return Promise.reject(err);
  }
);

export async function login(username: string, password: string) {
  const { data } = await api.post<{ access_token: string; user?: User }>("/api/auth/login", { username, password });
  setToken(data.access_token);
  const raw = data.user || (await api.get<User>("/api/auth/me")).data;
  const user = { ...raw, credits: raw.credits ?? raw.credit_balance ?? 0 };
  localStorage.setItem("tk_electron_user", JSON.stringify(user));
  return user;
}

export async function smsSendCode(phone: string) {
  return (await api.post("/api/auth/sms/send", { phone })).data;
}

export async function smsLogin(phone: string, code: string) {
  const { data } = await api.post<{ access_token: string; user: User }>("/api/auth/sms/login", { phone, code });
  setToken(data.access_token);
  const user = { ...data.user, credits: data.user.credits ?? data.user.credit_balance ?? 0 };
  localStorage.setItem("tk_electron_user", JSON.stringify(user));
  return user;
}

export function logout() {
  setToken(null);
  localStorage.removeItem("tk_electron_user");
}

export const getUser = () => api.get<User>("/api/auth/me").then((r) => r.data);
export const getRecommendations = (limit = 12) => api.get<Product[]>(`/api/derived-recommendations?limit=${limit}`).then((r) => r.data || []);
export const getRegions = () => api.get<Array<{ region_name?: string; region_code?: string }>>("/api/regions").then((r) => r.data || []);
export const getRanks = (params: Record<string, string | number | boolean>) => api.get("/api/daily-recommendations", { params }).then((r) => r.data);
export const syncConfiguredRanks = () => api.post("/api/fastmoss/sync-configured").then((r) => r.data);
export const getLibrary = () => api.get<Product[]>("/api/ai/search-results").then((r) => r.data || []);
export const getFavorites = () => api.get<Product[]>("/api/favorites").then((r) => r.data || []);
export const getTeacherProducts = () => api.get<Product[]>("/api/teacher/products").then((r) => r.data || []);
export const getTeacherDerived = (productId: number | string) => api.get<Product[]>(`/api/teacher/products/${productId}/derived-products`).then((r) => r.data || []);
export const getDerivedProducts = (productId: number | string) => api.get<Product[]>(`/api/ai/products/${productId}/derived-products`).then((r) => r.data || []);
export const generateDerived = (productId: number | string) => api.post(`/api/ai/products/${productId}/generate-derived`).then((r) => r.data);
export const addLibraryProduct = (product: Product) => api.post("/api/ai/library-products", { product }).then((r) => r.data);
export const getSelectionAttributes = () => api.get<Array<{ id: number; name?: string; label?: string; enabled?: boolean }>>("/api/selection-attributes").then((r) => r.data || []);
export const rejectDerived = (id: number | string, attributeIds: number[], reviewComment: string) => api.post(`/api/teacher/derived-products/${id}/reject`, { attribute_ids: attributeIds, review_comment: reviewComment });
export const collect = (product: Product) => api.post("/api/favorites", {
  source_type: product.source_type || (product.list_type ? "new_product" : "derived"),
  title: product.title || product.derived_title || "",
  image_url: product.image_url || product.supplier_image_url || "",
  price: Number(product.price ?? product.supplier_price ?? 0),
  currency: product.currency || (product.region === "CN" ? "CNY" : product.region === "JP" ? "JPY" : ""),
  sales_count: Number(product.sales_count ?? product.supplier_sales_count ?? 0),
  category: product.category || "",
  recommendation_reason: product.recommendation_reason || "",
  analysis_report: product.analysis_report || {},
  product_snapshot: product,
});
export const removeFavorite = (id: number | string) => api.delete(`/api/favorites/${id}`);
export const searchSelection = (message: string, count: number) => api.post<{ task_id?: number; credit_balance?: number; message?: string }>("/api/ai/chat-selection", { message, count }).then((r) => r.data);
export const createSelectionPipelineTask = (message: string, options: { mode?: "selection" | "derivation"; source_product_id?: number | string } = {}) => api.post<{ task_id?: number; status?: string; stage?: string; progress?: number }>("/api/selection-pipeline/tasks", { message, ...options }).then((r) => r.data);
export const getLatestSelectionPipelineTask = () => api.get<{ task_id?: number | null }>("/api/selection-pipeline/tasks/latest").then((r) => r.data);
export const getSelectionPipelineTask = (taskId: number | string) => api.get(`/api/selection-pipeline/tasks/${taskId}`).then((r) => r.data);
export const getSelectionPipelineReportContent = (taskId: number | string) => api.post(`/api/selection-pipeline/tasks/${taskId}/report-content`).then((r) => r.data);
export const getSelectionTask = (taskId: number | string) => api.get(`/api/ai/selection-tasks/${taskId}`).then((r) => r.data);
export const changePassword = (old_password: string, new_password: string) => api.post("/api/auth/change-password", { old_password, new_password });
export const getUsers = () => api.get<User[]>("/api/admin/users").then((r) => r.data || []);
export const createUser = (payload: Record<string, unknown>) => api.post<User>("/api/admin/users", payload).then((r) => r.data);
export const updateUser = (id: number, payload: Record<string, unknown>) => api.put<User>(`/api/admin/users/${id}`, payload).then((r) => r.data);
export const setUserStatus = (id: number, status: number) => api.patch(`/api/admin/users/${id}/status`, { status });
export const rechargeUser = (id: number, credits: number, remark = "") => api.post(`/api/admin/users/${id}/credits/recharge`, { credits, remark }).then((r) => r.data);
export const deleteUser = (id: number) => api.delete(`/api/admin/users/${id}`);
export const resetUserPassword = (id: number, password = "123456") => api.post(`/api/admin/users/${id}/reset-password`, { password }).then((r) => r.data);
export const getModelConfigs = () => api.get<ConfigItem[]>("/api/admin/model-configs").then((r) => r.data || []);
export const createModelConfig = (payload: Record<string, unknown>) => api.post<ConfigItem>("/api/admin/model-configs", payload).then((r) => r.data);
export const updateModelConfig = (id: number, payload: Record<string, unknown>) => api.put<ConfigItem>(`/api/admin/model-configs/${id}`, payload).then((r) => r.data);
export const setModelStatus = (id: number, status: number) => api.patch(`/api/admin/model-configs/${id}/status`, { status });
export const deleteModelConfig = (id: number) => api.delete(`/api/admin/model-configs/${id}`);
export const testModelConfig = (id: number, text: string, image_url = "") => api.post(`/api/admin/model-test`, { model_config_id: id, text, image_url }, { timeout: 480000 }).then((r) => r.data);
export const getThirdPartyConfigs = () => api.get<ConfigItem[]>("/api/admin/third-party-configs").then((r) => r.data || []);
export const createThirdPartyConfig = (payload: Record<string, unknown>) => api.post<ConfigItem>("/api/admin/third-party-configs", payload).then((r) => r.data);
export const updateThirdPartyConfig = (id: number, payload: Record<string, unknown>) => api.put<ConfigItem>(`/api/admin/third-party-configs/${id}`, payload).then((r) => r.data);
export const setThirdPartyStatus = (id: number, status: number) => api.patch(`/api/admin/third-party-configs/${id}/status`, { status });
export const deleteThirdPartyConfig = (id: number) => api.delete(`/api/admin/third-party-configs/${id}`);
export const testEchoTik = (payload: { operation: "photo_search" | "detail"; image_url?: string; product_ids?: string[]; region?: string }) => api.post("/api/admin/third-party-configs/echotik-test", payload, { timeout: 120000 }).then((r) => r.data);
export const getSelectionAttributesAdmin = () => api.get<Record<string, unknown>[]>("/api/admin/selection-attributes").then((r) => r.data || []);
export const createSelectionAttribute = (payload: Record<string, unknown>) => api.post("/api/admin/selection-attributes", payload).then((r) => r.data);
export const updateSelectionAttribute = (id: number, payload: Record<string, unknown>) => api.put(`/api/admin/selection-attributes/${id}`, payload).then((r) => r.data);
export const setSelectionAttributeStatus = (id: number, status: number) => api.patch(`/api/admin/selection-attributes/${id}/status`, { status });
export const deleteSelectionAttribute = (id: number) => api.delete(`/api/admin/selection-attributes/${id}`);
export const getPromptConstants = () => api.get<Record<string, unknown>[]>("/api/admin/prompt-constants").then((r) => r.data || []);
export const getSmartSelectionIntro = () => getPromptConstants().then((items) => String(items.find((item) => item.constant_key === "smart_selection_intro" && Number(item.status ?? 1) === 1)?.constant_content || ""));
export const createPromptConstant = (payload: Record<string, unknown>) => api.post("/api/admin/prompt-constants", payload).then((r) => r.data);
export const updatePromptConstant = (id: number, payload: Record<string, unknown>) => api.put(`/api/admin/prompt-constants/${id}`, payload).then((r) => r.data);
export const setPromptConstantStatus = (id: number, status: number) => api.patch(`/api/admin/prompt-constants/${id}/status`, { status });
export const deletePromptConstant = (id: number) => api.delete(`/api/admin/prompt-constants/${id}`);
export const getRestrictionRules = () => api.get<Record<string, unknown>[]>("/api/admin/selection-restriction-rules").then((r) => r.data || []);
export const createRestrictionRule = (payload: Record<string, unknown>) => api.post("/api/admin/selection-restriction-rules", payload).then((r) => r.data);
export const updateRestrictionRule = (id: number, payload: Record<string, unknown>) => api.put(`/api/admin/selection-restriction-rules/${id}`, payload).then((r) => r.data);
export const setRestrictionRuleStatus = (id: number, status: number) => api.put(`/api/admin/selection-restriction-rules/${id}`, { status });
export const deleteRestrictionRule = (id: number) => api.delete(`/api/admin/selection-restriction-rules/${id}`);
export const getSystemSettings = () => api.get<Record<string, unknown>>("/api/admin/system-settings").then((r) => r.data || {});
export const getAppReleases = () => api.get<ConfigItem[]>("/api/admin/app-releases").then((r) => r.data || []);
export const updateSystemSettings = (values: Record<string, string>) => api.put("/api/admin/system-settings", { values }).then((r) => r.data);
export const uploadAppRelease = (payload: { version: string; release_notes: string; force_update: boolean; package: File }) => { const form = new FormData(); form.append("version", payload.version); form.append("release_notes", payload.release_notes); form.append("force_update", payload.force_update ? "1" : "0"); form.append("package", payload.package); return api.post("/api/admin/app-releases/upload", form, { timeout: 900000 }).then((r) => r.data); };
export const publishAppRelease = (id: number) => api.patch(`/api/admin/app-releases/${id}/publish`).then((r) => r.data);
export const deleteAppRelease = (id: number) => api.delete(`/api/admin/app-releases/${id}`);
export const approveDerived = (id: number | string) => api.post(`/api/teacher/derived-products/${id}/approve`);
export const getVideoProjects = () => api.get<VideoProject[]>("/api/video/projects").then((r) => r.data || []);
export const getVideoModels = () => api.get<Array<{ id?: number; label?: string; value?: string }>>("/api/video/models").then((r) => r.data || []);
export const createVideoProject = (payload: Record<string, unknown>) => api.post<VideoProject>("/api/video/projects", payload).then((r) => r.data);
export const updateVideoProject = (projectId: number, payload: Record<string, unknown>) => api.put<VideoProject>(`/api/video/projects/${projectId}`, payload).then((r) => r.data);
export const deleteVideoProject = (projectId: number) => api.delete(`/api/video/projects/${projectId}`);
export const uploadVideoAsset = (projectId: number, file: File, payload: Record<string, unknown>) => { const form = new FormData(); form.append("file", file); form.append("role", String(payload.role || "")); form.append("description", String(payload.description || "")); form.append("is_primary", String(payload.is_primary || 0)); return api.post<VideoProject>(`/api/video/projects/${projectId}/assets`, form).then((r) => r.data); };
export const updateVideoAsset = (projectId: number, assetId: number, payload: Record<string, unknown>) => api.put<VideoProject>(`/api/video/projects/${projectId}/assets/${assetId}`, payload).then((r) => r.data);
export const deleteVideoAsset = (projectId: number, assetId: number) => api.delete<VideoProject>(`/api/video/projects/${projectId}/assets/${assetId}`).then((r) => r.data);
export const generateVideoScript = (projectId: number) => api.post(`/api/video/projects/${projectId}/script/generate`).then((r) => r.data);
export const saveVideoScript = (projectId: number, payload: Record<string, unknown>) => api.put<VideoProject>(`/api/video/projects/${projectId}/script`, payload).then((r) => r.data);
export const submitVideoTask = (projectId: number, payload: Record<string, unknown>) => api.post(`/api/video/projects/${projectId}/tasks`, payload).then((r) => r.data);
export const refreshVideoTask = (projectId: number, taskId: number) => api.post(`/api/video/projects/${projectId}/tasks/${taskId}/refresh`).then((r) => r.data);
export const getPublishLatest = () => api.get("/api/auto-publish/latest").then((r) => r.data);
export const getPublishHistory = () => api.get("/api/auto-publish/history").then((r) => r.data || []);
export const getPublishTask = (taskId: string | number) => api.get(`/api/auto-publish/tasks/${taskId}`).then((r) => r.data);
export const getMiaoshouShops = (payload: Record<string, unknown>) => api.post("/api/auto-publish/miaoshou/shop-list", payload).then((r) => r.data);
export const reauthorizeMiaoshou = (storage_state: Record<string, unknown>) => api.post("/api/auto-publish/miaoshou/reauthorize-picture-space", { storage_state }).then((r) => r.data);
export const createPublishBatch = (payload: Record<string, unknown>) => api.post("/api/auto-publish/1688/batch-tasks", payload).then((r) => r.data);
export const runPublishTask = (taskId: string) => api.post(`/api/auto-publish/tasks/${taskId}/run-async`).then((r) => r.data);
export const getPipelineStatus = () => api.get("/api/pipeline/status").then((r) => r.data);
