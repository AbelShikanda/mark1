# GOAL
Build a WhatsApp marketing automation bot with a React + TypeScript web dashboard to demonstrate the Python + TypeScript + React stack for an upcoming interview.

## Success criteria
- Backend: Python + FastAPI + Playwright bot exposing a REST API (products, groups, campaigns, logs, analytics).
- Frontend: React + TypeScript + Vite + Tailwind dashboard consuming the API.
- Run both locally end-to-end: create product/group, start campaign, see logs + analytics in dashboard.
- Code is clean, committed, and pushable (no secrets, `.env` ignored).

## Out of scope
- Instagram / Facebook / Telegram / X posting (other socials deferred).
- User auth / multi-tenancy.
- Deployment / CI / billing.

## Decision on stack
- TypeScript + React (React written in TS) — hits all three stack requirements at once.
- FastAPI backend — async-friendly, matches existing skill list, ships OpenAPI docs.
- SQLite storage, Vite + Tailwind frontend (consistent with existing dubairest project).
