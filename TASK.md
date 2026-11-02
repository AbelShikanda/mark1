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
- [ ] backend/main.py FastAPI app: health, logs, products, groups, campaigns, analytics, campaign start
- [ ] Verify uvicorn runs and /docs loads
- [ ] Verify SQLite tables created at startup

## Phase 3 — frontend
- [ ] frontend/package.json + tsconfig + vite.config.ts + tailwind.config.js + index.html
- [ ] frontend/src/main.tsx + App.tsx + layout/nav
- [ ] frontend/src/api.ts (axios client to http://localhost:8000)
- [ ] Pages: Products, Groups, Campaigns, Analytics, Logs
- [ ] Wire pages to API

## Phase 4 — validation
- [ ] Run API + dashboard end-to-end
- [ ] Commit to git (no secrets)
- [ ] Push to GitHub
