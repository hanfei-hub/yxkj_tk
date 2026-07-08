# TK Selection Desktop

PySide6 MVP desktop client.

## Run

```bash
cd desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app/main.py
```

Demo accounts:

- admin / admin123
- teacher / teacher123
- student / student123

During development, the desktop client opens the main window directly and shows all menus. The bottom-left user area shows login status. Click Login there to open the login dialog.

If the backend is not running, the client uses local mock data so the UI can still be previewed.
