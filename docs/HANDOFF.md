# TK Cross-Border Selection App Handoff

This file is the project handoff note for continuing development after switching Codex accounts.

## Project Location

- Local workspace: `C:\Users\61655\Documents\Codex\2026-07-07\ni\work\tk_selection_app`
- Output exe path: `C:\Users\61655\Documents\Codex\2026-07-07\ni\outputs\TK跨境助手.exe`
- Git remote: `https://github.com/hanfei-hub/yxkj_tk.git`
- Current working branch: `hanfei`

## Runtime Shape

- Backend: FastAPI + SQLAlchemy.
- Desktop client: PySide6 Windows app.
- Server backend base URL used by the desktop app: `http://120.26.207.89`.
- Local backend startup is disabled; do not run a local backend.
- Desktop app can be started with `.\start_desktop.ps1`.

## Accounts

Demo accounts initialized by the backend seed logic:

- `admin / admin123`
- `teacher / teacher123`
- `student / student123`

## Important Security Notes

- Do not commit API keys, private keys, `.env` files, database dumps, or packaged `.exe` files.
- FastMoss API keys and model API keys should be configured through the admin UI and stored in the database.
- Server SSH private key is local machine state and must not be added to the repo.

## Current Product Logic

The product is a TikTok cross-border e-commerce selection tool for Japan.

Main roles:

- Admin: user management, model config, third-party API config, selection attributes, FastMoss sync.
- Teacher: hot product dashboard, derived product generation, derived product approval/rejection.
- Student: AI selection chat and product recommendation view.

Main data flow:

1. Admin triggers FastMoss sync.
2. Backend requests Japan new-listed products from FastMoss.
3. Backend clears old FastMoss product rows and inserts fresh products.
4. Product titles are translated to Simplified Chinese when a usable model config exists.
5. Frontend displays products from the backend.
6. Teacher clicks a source product and generates derived product directions.
7. Model generates derived directions and attribute scores.
8. Teacher approves or rejects a derived direction.
9. Review records are saved for later attribute weight learning.

## Recent Fixes To Preserve

- FastMoss title translation now prefers an active model config with API key/base URL/model name.
- FastMoss imported text fields are cleaned before saving.
- Desktop image loading now keeps raw image bytes as a fallback when PIL cannot decode WebP images.
- Product images are scaled to fit the card area.

## Known Follow-Ups

1. Unify model selection logic between FastMoss translation and AI generation.
2. Add a FastMoss sync log table for success/failure count, translation count, and error details.
3. Add scheduled daily FastMoss sync on the server.
4. Finish 1688 API integration after the third-party API format is finalized.
5. Add teacher review statistics and update `selection_attributes.current_weight`.
6. Improve frontend loading states for slow image/model calls.

