export type Role = "admin" | "teacher" | "student";

export interface User {
  id?: number;
  username?: string;
  real_name?: string;
  role: Role;
  credits?: number;
  credit_balance?: number;
}

export interface Product {
  id?: number | string;
  source_product_id?: number | string;
  title?: string;
  derived_title?: string;
  image_url?: string;
  supplier_image_url?: string;
  price?: number | string;
  supplier_price?: number | string;
  currency?: string;
  region?: string;
  category?: string;
  sales_count?: number;
  supplier_sales_count?: number;
  source_type?: string;
  list_type?: string;
  recommendation_reason?: string;
  analysis_report?: unknown;
  ai_score?: number | string;
  weighted_score?: number | string;
  supplier_match_score?: number | string;
  supplier_source_url?: string;
  supplier_product_id?: string | number;
  supplier_shop_name?: string;
  product_snapshot?: Record<string, unknown>;
  derived_count?: number;
}

export interface ConfigItem {
  id?: number;
  config_name?: string;
  provider?: string;
  model_type?: string;
  model_name?: string;
  base_url?: string;
  api_base_url?: string;
  status?: number;
  service_type?: string;
  key?: string;
  values?: Record<string, unknown>;
}

export interface VideoProject {
  id: number;
  user_id?: number;
  title?: string;
  target_market?: string;
  video_language?: string;
  product_details?: string;
  script_text?: string;
  script_json?: Record<string, unknown>;
  status?: string;
  result_video_url?: string;
  assets?: Array<{ id: number; public_url?: string; url?: string; asset_type?: string; role?: string; description?: string; is_primary?: number }>;
  storyboard?: Array<Record<string, unknown>>;
  tasks?: Array<{ id: number; status?: string; model_name?: string; provider_task_id?: string; video_url?: string; result_video_url?: string; error_message?: string; created_at?: string; updated_at?: string; usage_cost_cny?: number }>;
}
