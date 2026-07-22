# TK Selection Backend

Backend service for the TK Japan cross-border selection tool.

The backend now uses the server MySQL database only. Configure `DATABASE_URL` before startup:

```text
mysql+pymysql://USER:PASSWORD@HOST:3306/DB_NAME?charset=utf8mb4
```

Local SQLite fallback has been removed. If `DATABASE_URL` is missing or points to SQLite, startup will fail.

## Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
本地后端启动已禁用。请使用服务器后端：http://120.26.207.89
```

## Demo Accounts

- admin / admin123
- teacher / teacher123
- student / student123

## 1688 API adapter

The 1688 supplier layer is API-only. Create an enabled third-party config:

- `service_type`: `1688_api`
- `api_base_url`: provider base URL
- `access_key_encrypted`: API key or bearer token
- `secret_key_encrypted`: optional secret
- `remark`: optional JSON adapter settings

Example `remark`:

```json
{
  "search_path": "/search",
  "method": "POST",
  "keyword_field": "keyword",
  "page_field": "page",
  "page_size_field": "page_size",
  "items_path": "data.items",
  "total_path": "data.total"
}
```

Search endpoints:

- `POST /api/suppliers/1688/search`
- `POST /api/suppliers/1688/derived-products/{derived_id}/search`
