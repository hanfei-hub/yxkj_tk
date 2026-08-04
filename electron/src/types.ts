export type Role = "admin" | "teacher" | "student";

export interface User {
  id?: number;
  username?: string;
  real_name?: string;
  role: Role;
  credits?: number;
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
  analysis_report?: unknown;
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
  title?: string;
  target_market?: string;
  video_language?: string;
  status?: string;
  script_text?: string;
  assets?: Array<{ id: number; file_url?: string; role?: string }>;
}
