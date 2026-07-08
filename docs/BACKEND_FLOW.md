# Backend Flow

## Auth

`POST /api/auth/login`

Returns a JWT token. The desktop app sends the token with:

```http
Authorization: Bearer <token>
```

Role checks are done through `require_role(...)`.

## Admin APIs

Prefix: `/api/admin`

- `GET /users`
- `POST /users`
- `PUT /users/{user_id}`
- `PATCH /users/{user_id}/status`
- `POST /users/{user_id}/reset-password`
- `GET /model-configs`
- `POST /model-configs`
- `PUT /model-configs/{config_id}`
- `PATCH /model-configs/{config_id}/status`
- `POST /model-configs/{config_id}/default`
- `GET /third-party-configs`
- `POST /third-party-configs`
- `PUT /third-party-configs/{config_id}`
- `PATCH /third-party-configs/{config_id}/status`
- `GET /selection-attributes`
- `POST /selection-attributes`
- `PUT /selection-attributes/{attribute_id}`
- `PATCH /selection-attributes/{attribute_id}/status`

## FastMoss Sync

`POST /api/fastmoss/sync-products?page=1&pagesize=20`

Only admin can call it.

Current FastMoss request:

- Region: `JP`
- Cross-border product: yes
- Fully managed product: no
- Default date: today minus 4 days
- Config source: `third_party_configs`, `service_type = fastmoss`, `status = 1`

Import behavior:

- Clears old FastMoss `fm_products` rows first.
- Saves image URL, title, price, currency, sales count, rank, category, shop, source URL, and raw data.
- Currency is saved as `JPY`.
- Title translation tries to use a usable model config.
- Each sync writes one row to `fastmoss_sync_logs`, including request date, requested count, synced count, translation success/failure count, status, and error message.

`GET /api/fastmoss/sync-logs?limit=20`

Admin-only endpoint for reading recent FastMoss sync records.

## Product APIs

`GET /api/products/hot`

Used by both the student selection page and teacher dashboard. It returns `fm_products` sorted by rank.

`GET /api/daily-recommendations`

If FastMoss products exist, returns the first 10 products as recommendations.

## AI Selection Chat

`POST /api/ai/chat-selection`

Request:

```json
{
  "message": "selection requirement"
}
```

It calls the configured chat model. If model call fails, backend returns a local fallback answer.

## Derived Product Generation

`POST /api/ai/products/{product_id}/generate-derived`

Flow:

1. Load source product from `fm_products`.
2. Load active `selection_attributes`.
3. Build a prompt with product context and attribute context.
4. Call chat completion model and require JSON output.
5. Save rows to `derived_product_recommendations`.
6. Save per-attribute scores to `derived_product_attribute_scores`.
7. If model fails, save local-rule fallback derived directions.

## Teacher Review

`GET /api/teacher/products`

Returns teacher dashboard products.

`GET /api/teacher/products/{product_id}/derived-products`

Returns derived directions for one source product.

`POST /api/teacher/derived-products/{derived_id}/approve`

Marks derived direction as approved and inserts a review record.

`POST /api/teacher/derived-products/{derived_id}/reject`

Request:

```json
{
  "attribute_ids": [1, 2],
  "review_comment": "reason"
}
```

Marks derived direction as rejected and inserts a review record.

## 1688 Supplier Adapter

Prefix: `/api/suppliers`

- `POST /1688/search`
- `POST /1688/derived-products/{derived_id}/search`

Current status: adapter layer exists and expects a third-party 1688 API config in `third_party_configs` with `service_type = 1688_api`.

## Model Usage

Model config table: `model_configs`.

Important fields:

- `provider`
- `base_url`
- `api_key_encrypted`
- `model_name`
- `temperature`
- `max_tokens`
- `is_default`
- `status`

The backend uses OpenAI-compatible chat completion requests:

```text
POST {base_url}/chat/completions
Authorization: Bearer <api_key>
```

Model selection is centralized in `ai_model_service.py`. The current priority is:

1. Active and complete Doubao config.
2. Active and complete default config.
3. Any active and complete config.

FastMoss title translation and AI derived-product generation both use this same selection logic.

## Desktop Interaction

The desktop app centralizes backend calls in `desktop/app/main.py`, class `DataGateway`.

Important mappings:

- `hot_products()` -> `GET /api/products/hot`
- `daily_recommendations()` -> `GET /api/daily-recommendations`
- `ai_chat()` -> `POST /api/ai/chat-selection`
- `generate_derived_products()` -> `POST /api/ai/products/{id}/generate-derived`
- `derived_products()` -> `GET /api/teacher/products/{id}/derived-products`
- `approve()` -> `POST /api/teacher/derived-products/{id}/approve`
- `reject()` -> `POST /api/teacher/derived-products/{id}/reject`
- `model_configs()` -> `GET /api/admin/model-configs`
- `third_party_configs()` -> `GET /api/admin/third-party-configs`
- `sync_fastmoss_products()` -> `POST /api/fastmoss/sync-products?page=1&pagesize=20`
