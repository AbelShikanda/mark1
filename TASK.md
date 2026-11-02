# TASKS

## Phase 1 — scaffold (done)
- [x] Create directory structure (backend/bot, frontend/src/pages|components|assets|public)
- [x] Root .gitignore, README.md
- [x] backend/.env.example, config.py, models.py
- [x] backend/db_logic.py (SQLite schema + logs)
- [x] backend/requirements.txt
- [x] backend/bot modules: login_manager, group_manager, group_poster, group_link_marketer, contact_messenger, analytics_module, target_groups, target_audience, setup_data_dirs, __init__
- [x] GOAL.md, DECISION.md

## Phase 2 — backend API
- [x] backend/main.py FastAPI app: health, logs, products, groups, campaigns, analytics, campaign start
- [x] Verify Python files compile (py_compile OK)
- [~] Runtime uvicorn blocked: pydantic-core has no Python 3.14 wheel (build too slow). Works on Python 3.11/3.12 where wheels exist.

## Phase 3 — frontend
- [x] frontend/package.json + tsconfig + vite.config.ts + tailwind.config.js + index.html
- [x] frontend/src/main.tsx + App.tsx + layout/nav
- [x] frontend/src/api.ts (axios client to http://localhost:8000)
- [x] Pages: Products, Groups, Campaigns, Analytics, Logs
- [x] Wire pages to API
- [x] `npm run build` passes (tsc + vite)

## Phase 4 — validation
- [x] Frontend builds cleanly; backend compiles
- [x] Committed to git (no secrets)
- [ ] Push to GitHub (user to run remote add + push)
