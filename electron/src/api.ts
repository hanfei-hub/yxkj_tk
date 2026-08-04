import axios from "axios";
import type { ConfigItem, Product, User, VideoProject } from "./types";

const defaultBase = "http://120.26.207.89";
const baseURL = localStorage.getItem("tk_api_base") || defaultBase;
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

export async function login(username: string, password: string) {
  const { data } = await api.post<{ access_token: string; user?: User }>("/api/auth/login", { username, password });
  setToken(data.access_token);
  const user = data.user || (await api.get<User>("/api/auth/me")).data;
  localStorage.setItem("tk_electron_user", JSON.stringify(user));
  return user;
}

export function logout() {
  setToken(null);
  localStorage.removeItem("tk_electron_user");
}

export const getUser = () => api.get<User>("/api/auth/me").then((r) => r.data);
export const getRecommendations = (limit = 12) => api.get<Product[]>(`/api/derived-recommendations?limit=${limit}`).then((r) => r.data || []);
export const getRanks = (params: Record<string, string | number | boolean>) => api.get("/api/daily-recommendations", { params }).then((r) => r.data);
export const getLibrary = () => api.get<Product[]>("/api/ai/search-results").then((r) => r.data || []);
export const getFavorites = () => api.get<Product[]>("/api/favorites").then((r) => r.data || []);
export const getTeacherProducts = () => api.get<Product[]>("/api/teacher/products").then((r) => r.data || []);
export const getTeacherDerived = (productId: number | string) => api.get<Product[]>(`/api/teacher/products/${productId}/derived-products`).then((r) => r.data || []);
export const getSelectionAttributes = () => api.get<Array<{ id: number; name?: string; label?: string; enabled?: boolean }>>("/api/selection-attributes").then((r) => r.data || []);
export const rejectDerived = (id: number | string, attributeIds: number[], reviewComment: string) => api.post(`/api/teacher/derived-products/${id}/reject`, { attribute_ids: attributeIds, review_comment: reviewComment });
export const collect = (product: Product) => api.post("/api/favorites", { product });
export const removeFavorite = (id: number | string) => api.delete(`/api/favorites/${id}`);
export const searchSelection = (message: string, count: number) => api.post("/api/ai/chat-selection", { message, count });
export const changePassword = (old_password: string, new_password: string) => api.post("/api/auth/change-password", { old_password, new_password });
export const getUsers = () => api.get<User[]>("/api/admin/users").then((r) => r.data || []);
export const getModelConfigs = () => api.get<ConfigItem[]>("/api/admin/model-configs").then((r) => r.data || []);
export const getThirdPartyConfigs = () => api.get<ConfigItem[]>("/api/admin/third-party-configs").then((r) => r.data || []);
export const getSystemSettings = () => api.get<Record<string, unknown>>("/api/admin/system-settings").then((r) => r.data || {});
export const getAppReleases = () => api.get<ConfigItem[]>("/api/admin/app-releases").then((r) => r.data || []);
export const approveDerived = (id: number | string) => api.post(`/api/teacher/derived-products/${id}/approve`);
export const getVideoProjects = () => api.get<VideoProject[]>("/api/video/projects").then((r) => r.data || []);
export const createVideoProject = (payload: Record<string, unknown>) => api.post<VideoProject>("/api/video/projects", payload).then((r) => r.data);
export const generateVideoScript = (projectId: number) => api.post(`/api/video/projects/${projectId}/script/generate`).then((r) => r.data);
export const submitVideoTask = (projectId: number, payload: Record<string, unknown>) => api.post(`/api/video/projects/${projectId}/tasks`, payload).then((r) => r.data);
export const getPublishLatest = () => api.get("/api/auto-publish/latest").then((r) => r.data);
export const getPublishHistory = () => api.get("/api/auto-publish/history").then((r) => r.data || []);
export const createPublishBatch = (payload: Record<string, unknown>) => api.post("/api/auto-publish/1688/batch-tasks", payload).then((r) => r.data);
export const runPublishTask = (taskId: string) => api.post(`/api/auto-publish/tasks/${taskId}/run-async`).then((r) => r.data);
export const getPipelineStatus = () => api.get("/api/pipeline/status").then((r) => r.data);
