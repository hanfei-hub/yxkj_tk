# TK Selection Backend

MVP backend skeleton for the TK Japan cross-border selection tool.

The backend now uses local SQLite by default:

```text
data/tk_selection.db
```

The database is created automatically on startup with demo seed data.

## Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
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
