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
