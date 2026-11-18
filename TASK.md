# TASKS

## Phase 1 — scaffold (done)
- [x] Create directory structure (backend/bot, frontend/src/pages|components|assets|public)
- [x] Root .gitignore, README.md
- [x] backend/.env.example, config.py, models.py
- [x] backend/db_logic.py (SQLite schema + logs)
- [x] backend/requirements.txt
- [x] backend/bot modules: login_manager, campaign_runner, __init__ (legacy group-poster modules removed)
- [x] GOAL.md, DECISION.md, TASK.md

## Phase 2 — backend API (done, reworked for WhatsApp spec)
- [x] backend/main.py FastAPI app: health, logs, products, groups, clients, campaigns, schedules, analytics, campaign start/stop/cancel
- [x] bot/campaign_runner.py: product/group/client posting, equitable-random categories, isPosted/isNotPosted/isPending, group daily limit n, busy handling, time-blocking schedules, campaign_posts + analytics recording
- [x] bot/login_manager.py headed Chrome/Playwright (visible window)
- [x] Verify Python files compile (py_compile OK)
- [x] Desktop shortcut: Marketing Bot.lnk (hidden; builds the UI and starts one server on :8000)

## Phase 3 — frontend (done, reworked for WhatsApp spec)
- [x] frontend/package.json + tsconfig + vite.config.ts + tailwind.config.js + index.html
- [x] frontend/src/main.tsx + App.tsx + layout/nav
- [x] frontend/src/api.ts (axios client)
- [x] Pages: Products, Groups, Clients, Campaigns, Schedules, Analytics, Logs
- [x] Wire pages to API
- [x] `npm run build` passes (tsc + vite)

## Phase 4 — validation
- [x] Frontend builds cleanly; backend compiles
- [x] Committed to git (no secrets)
- [ ] Push to GitHub (user to run remote add + push)

## Phase 5 — refined behaviour (done)
- [x] Product edit + delete API/UI; optional description; image sent as an attachment.
- [x] Products reset to isNotPosted when the last one is posted (end of run).
- [x] Campaigns: all-groups/all-clients scope with a non-repeating batch cursor; a single run loops all batches until the cycle is covered; auto product by category.
- [x] Product→clients campaigns can target one or many selected clients (campaign_clients join table).
- [x] Campaign-generated schedules, overlap push-forward, repeat daily/weekly/monthly, rePost.
- [x] isPending lifecycle for fixed products on scheduled campaigns.
- [x] Busy campaigns move to the next free slot; cooperative cancel while running.
- [x] Groups: is_core, failures/auto-disable, enable/disable, edit; my-group links as link sources.
- [x] Link campaigns: core priority sources, core excluded targets, batch cursor, no repeats until the cycle ends.
- [x] Sync Playwright login manager ported from the reference (strict connection states, popups, recovery, cooperative cancel).
- [x] Poster ported from the reference (3 open attempts, Shift+Enter line breaks, link-preview wait, send confirmation, image attach).
- [x] Idempotent group seeder with case-insensitive dedupe, region/topic detection, JSON upload + CLI.
- [x] Offline engine simulation (batching, link targeting, pending, repeat, defer) and headless UI E2E pass.

## Phase 6 — group data
- [x] Import the original `target_groups.py` lists (CORE_GROUPS / MARKETING_GROUPS / GROUP_CATEGORIES)
      and verify region/category mapping in the Seeder. 367 unique groups seeded (51 core); case-insensitive dedupe is clean.
- [ ] Live WhatsApp smoke test with a test account (login, image post, link preview, cancel).

## Phase 7 — product data
- [x] Idempotent product seeder (`backend/seed_products.py`) for the WhatsApp and Instagram
      adoption exports: 179 unique products (116 WhatsApp + 63 Instagram), exact-link dedupe,
      blank-field-only updates, invalid-link warnings, and `--dry-run` / `--preserve-status` /
      `--all-pending` flags.
- [x] `POST /admin/seed-products` endpoint and **Seed products** button with a summary
      (inserted / updated / skipped / candidates); no automatic seeding at startup.
- [x] Products page search + status filter for the larger product list.
- [x] Verified on a temporary DB copy: 179 inserted, 30 posted / 149 not posted (the 4 existing
      products untouched), second run inserts 0, and `GET /products` returns all rows.
- [ ] Review imported product names/categories and add captions or images where wanted.

## Phase 8 — reusable group batches (done)
- [x] `group_batches`, `group_batch_members`, `campaign_group_batches` tables (additive migration).
- [x] `GET/POST/PATCH/DELETE /group-batches` with case-insensitive name dedupe, group validation,
      live membership updates, and a 409 when a batch is still used by campaigns.
- [x] `product_group` campaigns support `target_scope = "batch"` with multiple `batch_ids`; batch
      scope stores `group_id = NULL` and resets the group cursor when scope/batch size changes.
- [x] Runner resolves batch membership at run time (union, de-duplicated, active/capped filtered)
      and paces the whole cycle without repeating a group early.
- [x] Groups page batch CRUD UI (searchable group picker, select all/clear, badges, usage count).
- [x] Campaigns page batch selection/editing, combined unique group count, and target summaries.
- [x] README section; single-group, all-groups, product_client and myGroupLink paths unchanged.
## Phase 9 � live priorities (added 2026-11-18)

### High
- [x] Feedback page: in-app suggestion box for bugs/improvements � type, title, description, steps to reproduce, expected/actual, screenshot upload to uploads/, stored in a `feedback` table; dashboard page; one-click "copy as markdown issue" export (environment, steps, evidence) ready to paste to an agent
- [x] Message capture during campaign runs (opt-in per campaign): per-campaign `capture_replies` toggle + `capture_dwell_seconds` per group with a global default in Settings (default 0 / disabled); capture only after a confirmed-sent post; DOM scrape after the dwell; raw rows stored in a `group_messages` table linked to campaign_posts/run_id; capture failures can never fail the post/campaign
- [x] Retention: Settings field `message_retention_days` (default e.g. 30) auto-purges raw captured messages; generated reports/conclusions are retained until manually removed
- [x] Reports: define what a report contains (candidate: saved analysis snapshot � intent/sentiment summary, top questions, leaderboards, best time) and add on-demand generation + retained-list UI; confirm definition with user first
- [x] Message classification (local, offline): intent/topic/sentiment via keyword rules in English/Swahili/Sheng; stored per captured message; feeds the reports
- [x] Analytics on captured data: best posting time, group leaderboard, post leaderboard (depends on capture + classification)
- [ ] Deferred (not scheduled): per-link click tracking � needs an external redirector (e.g. self-hosted Cloudflare Worker, free tier); revisit when analytics core lands

## Phase 10 - Kali / Linux support
- [ ] start.sh + .desktop launcher (builds frontend, starts server on :8000, opens browser)
- [ ] stop script (kill venv python + chromium PIDs on port flow, Linux equivalent of stop-server.ps1)
- [ ] Linux branch in force_kill_browser_processes (pkill/pgrep on chromium PIDs whose cmdline references whatsapp_session)
- [ ] Document/verify playwright install --with-deps chromium on Kali (apt system libraries)
- [ ] Decide root-user handling: document "run as normal user" OR add --no-sandbox when euid==0
- [ ] Linux splash equivalent or drop splash on Linux (shell-friendly banner)
- [ ] Test full campaign run + Stop + Kill Server on a Kali machine (or container) end to end
- [ ] Validate config.py browser path fallback on Linux (~/.cache/ms-playwright vs BASE_DIR/ms-playwright)
