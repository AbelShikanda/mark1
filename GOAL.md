# GOAL
Build a WhatsApp marketing automation bot with a React + TypeScript web dashboard to demonstrate the Python + TypeScript + React stack for an upcoming interview. Includes a hidden desktop shortcut that builds the UI and starts one server (API + dashboard on the same origin), and campaigns that start/stop a visible Chrome (Playwright) browser.

## Success criteria
- Backend: Python + FastAPI + Playwright bot exposing a REST API (products, groups, clients, campaigns, schedules, logs, analytics).
- Frontend: React + TypeScript + Vite + Tailwind dashboard consuming the API.
- Database schema matches WhatsApp spec: products (isPosted/isNotPosted/isPending, category nullable), groups (n limit, is_my_group, link nullable), clients (name, number, category, location, birthdays), campaigns (statuses, rePost, repeatPost, frequency), schedules (time blocking, no overlaps).
- Run both locally end-to-end through the desktop shortcut (hidden): shortcut builds the UI, starts the single FastAPI server on :8000, and opens it. Dev mode (Vite :5173) remains available manually.
- Campaigns: per-campaign Run/Stop/Cancel buttons; busy state handling that pushes to the next free slot; campaign-generated time blocks; no overlapping schedules.
- Products can be edited or deleted without re-creating them; images are attached to the WhatsApp message.
- A campaign can target one group/client or every group/client in non-repeating batches, and can repeat daily/weekly/monthly.
- Link campaigns source only "my groups" that have links; core groups are priority sources and excluded targets.
- The large group lists are seeded idempotently with case-insensitive deduplication and region/topic mapping.
- Code is clean, committed, and pushable (no secrets, `.env` ignored).

## Out of scope
- Instagram / Facebook / Telegram / X posting (other socials deferred).
- User auth / multi-tenancy.
- Deployment / CI / billing.

## Decision on stack
- TypeScript + React (React written in TS) — hits all three stack requirements at once.
- FastAPI backend — async-friendly, matches existing skill list, ships OpenAPI docs.
- SQLite storage, Vite + Tailwind frontend (consistent with existing dubairest project).
- Playwright headed Chromium for WhatsApp Web automation.
