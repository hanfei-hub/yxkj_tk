# 接口与数据表文档

## 1. 鉴权

### 登录

```text
POST /api/auth/login
```

请求：

```json
{
  "username": "admin",
  "password": "admin123"
}
```

返回：

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": {}
}
```

前端后续请求使用：

```http
Authorization: Bearer <access_token>
```

### 当前用户

```text
GET /api/auth/me
```

### 退出

```text
POST /api/auth/logout
```

## 2. 管理员接口

前缀：

```text
/api/admin
```

### 用户管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/users` | 用户列表 |
| POST | `/users` | 创建用户 |
| PUT | `/users/{user_id}` | 更新用户 |
| PATCH | `/users/{user_id}/status` | 启用/禁用用户 |
| POST | `/users/{user_id}/reset-password` | 重置密码 |

### 模型配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/model-configs` | 模型配置列表 |
| POST | `/model-configs` | 新增模型配置 |
| PUT | `/model-configs/{config_id}` | 更新模型配置 |
| PATCH | `/model-configs/{config_id}/status` | 启用/禁用模型 |
| POST | `/model-configs/{config_id}/default` | 设置默认模型 |

### 第三方 API 配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/third-party-configs` | 第三方配置列表 |
| POST | `/third-party-configs` | 新增第三方配置 |
| PUT | `/third-party-configs/{config_id}` | 更新第三方配置 |
| PATCH | `/third-party-configs/{config_id}/status` | 启用/禁用第三方配置 |

### 选品属性

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/selection-attributes` | 选品属性列表 |
| POST | `/selection-attributes` | 新增选品属性 |
| PUT | `/selection-attributes/{attribute_id}` | 更新选品属性 |
| PATCH | `/selection-attributes/{attribute_id}/status` | 启用/禁用选品属性 |

当前正式使用 8 条系统属性，不建议随意新增重复属性。

## 3. 公共选品属性接口

```text
GET /api/selection-attributes
POST /api/selection-attributes
```

允许角色：

- 管理员。
- 老师。
- 学生。

## 4. 商品接口

### 热门/新品商品

```text
GET /api/products/hot
```

用途：

- 智能选品页面。
- 教师看板。

### 每日推荐

```text
GET /api/daily-recommendations
```

当前逻辑：

- 如果 FastMoss 商品存在，优先返回 FastMoss 商品。
- 后续会逐步改成返回衍生品推荐。

### FastMoss 同步

```text
POST /api/fastmoss/sync-products?page=1&pagesize=20
```

允许角色：

- 管理员。

### FastMoss 同步日志

```text
GET /api/fastmoss/sync-logs?limit=20
```

## 5. AI 接口

### AI 智能选品对话

```text
POST /api/ai/chat-selection
```

请求：

```json
{
  "message": "我想找日本市场适合短视频展示的解压玩具"
}
```

### 单个原商品生成衍生品

```text
POST /api/ai/products/{product_id}/generate-derived
```

说明：

- 根据指定 FastMoss 商品生成衍生品。
- 当前正式链路更推荐通过后台任务批量生成。

## 6. 教师接口

前缀：

```text
/api/teacher
```

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/products` | 教师看板原商品 |
| GET | `/products/{product_id}/derived-products` | 某个原商品的衍生品 |
| POST | `/derived-products/{derived_id}/approve` | 通过衍生品 |
| POST | `/derived-products/{derived_id}/reject` | 拒绝衍生品 |
| GET | `/review-records` | 审核记录 |

拒绝请求：

```json
{
  "attribute_ids": [2],
  "review_comment": "商品周期性不符合"
}
```

## 7. 1688 货源接口

前缀：

```text
/api/suppliers
```

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/1688/search` | 直接搜索 1688 |
| POST | `/1688/derived-products/{derived_id}/search` | 根据衍生品搜索 1688 |
| POST | `/1688/derived-products/{derived_id}/auto-match` | 单个衍生品自动匹配 1688 |
| POST | `/1688/derived-products/auto-match` | 批量匹配待处理衍生品 |

## 8. 流水线接口

前缀：

```text
/api/pipeline
```

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/status` | 查看任务状态 |
| POST | `/derivations/queue` | 将待生成衍生品的原商品加入生成任务 |
| POST | `/suppliers/1688/queue` | 将待匹配 1688 的衍生品加入任务 |
| POST | `/suppliers/1688/run-now` | 立即执行一批 1688 匹配 |

## 9. 核心数据表

### users

用户表。

关键字段：

- `username`
- `password_hash`
- `real_name`
- `role`
- `status`
- `last_login_at`

### model_configs

大模型配置表。

关键字段：

- `provider`
- `base_url`
- `api_key_encrypted`
- `model_name`
- `temperature`
- `max_tokens`
- `is_default`
- `status`

### third_party_configs

第三方 API 配置表。

关键字段：

- `service_type`
- `api_base_url`
- `access_key_encrypted`
- `secret_key_encrypted`
- `remark`
- `status`

常用 `service_type`：

- `fastmoss`
- `1688_api`

### fm_products

FastMoss 商品表。

关键字段：

- `family_id`
- `fm_product_id`
- `region`
- `platform`
- `list_type`
- `title`
- `image_url`
- `price`
- `currency`
- `sales_count`
- `rank_no`
- `category`
- `shop_name`
- `source_url`
- `data_date`
- `raw_data`

### product_families

商品分族表。

关键字段：

- `family_key`
- `family_group`
- `family_variant`
- `family_name`
- `category_path`
- `normalized_keywords`
- `match_rule`

### selection_attributes

选品属性表。

当前系统属性：

| id | code | name |
| --- | --- | --- |
| 1 | dimension_1 | 使用场景 |
| 2 | dimension_2 | 商品周期性 |
| 3 | dimension_3 | 目标群体 |
| 4 | dimension_4 | 短视频流量种草适配能力 |
| 5 | dimension_5 | 日本市场偏好 |
| 6 | dimension_6 | 是否属于新奇特商品 |
| 7 | dimension_7 | 复购属性 |
| 8 | dimension_8 | 竞品属性 |

### product_family_dimension_weights

商品分族维度权重表。

关键字段：

- `family_id`
- `dimension_code`
- `dimension_name`
- `weight_percent`
- `reject_count`
- `approve_count`
- `total_review_count`

### derived_product_recommendations

衍生品推荐表。

关键字段：

- `family_id`
- `source_product_id`
- `derived_title`
- `derived_description`
- `recommendation_reason`
- `target_audience`
- `usage_scene`
- `risk_notes`
- `analysis_report`
- `source_search_keywords`
- `match_tags`
- `model_used`
- `ai_score`
- `weighted_score`
- `supplier_*`
- `review_status`
- `reviewed_by`
- `reviewed_at`

### derived_product_dimension_reports

衍生品 8 维度分析报告表。

关键字段：

- `recommendation_id`
- `family_id`
- `dimension_code`
- `dimension_name`
- `rating_level`
- `analysis_content`
- `weight_percent_snapshot`

### teacher_review_records

老师审核记录表。

关键字段：

- `teacher_id`
- `source_product_id`
- `recommendation_id`
- `review_result`
- `selected_attribute_ids`
- `review_comment`
- `review_snapshot`
- `created_at`

### fastmoss_sync_logs

FastMoss 同步日志表。

关键字段：

- `status`
- `request_date`
- `page`
- `pagesize`
- `requested_count`
- `synced_count`
- `translation_success_count`
- `translation_failed_count`
- `error_message`
- `request_snapshot`
- `response_snapshot`
- `started_at`
- `finished_at`

