# Marketing Bot

WhatsApp marketing automation bot built with Python + Playwright, served through a
FastAPI backend that also serves the React + TypeScript dashboard from the same origin.

## Stack
- **Backend:** Python 3.12+, FastAPI, Playwright (headed Chromium), pydantic, SQLite, python-dotenv
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, axios

## Run it (what the end user sees)

Double-click the **Marketing Bot** desktop shortcut, or run:

```bat
run.bat
```

That is the single production-style runtime:

1. builds the current frontend into `frontend/dist`
2. starts FastAPI on `http://127.0.0.1:8000`
3. serves the API, the dashboard and uploaded media from that one origin
4. opens the browser

One app, one origin, one database: `data/marketing.db` (path is shown by `/health`).

Clicking **Marketing Bot** again while the app is already running opens another browser
tab; it does not start a second server. If a launch is still building, a second click
waits for that server instead of starting a duplicate build.

To stop the app, either:

- double-click `stop.bat` in the project folder, or
- open Task Manager → **Details**, find `python.exe` with `main.py` in its command line
  (the one under `backend\venv\Scripts`), right-click → **End process tree**.

Launcher activity goes to `run.log`; the server's own output goes to `backend.log`
(both are ignored by git).

## Development (optional)

The shortcut **never** uses the dev server — it always shows the built app.
For hot-reload work, start the two dev processes manually:

```bash
# terminal 1
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

# terminal 2
cd frontend
npm run dev
```

Dev uses `frontend/.env.development` (`VITE_API_BASE=http://localhost:8000`) and opens
`http://localhost:5173`. Production builds are same-origin and need no API base.

## First-time setup

```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
playwright install chromium

cd ..\frontend
npm install
```

## Seeding groups

Drop the original `target_groups.py` into `backend/` (it may expose `CORE_GROUPS`,
`MARKETING_GROUPS`, `GROUP_CATEGORIES` and optionally `GROUP_LINKS`), then either:

- restart the app — seeding is idempotent and runs automatically when the file is present;
- run `.\venv\Scripts\python.exe seed_groups.py` from `backend/`;
- upload a JSON seed file from the Groups page (or `POST /admin/seed-groups/upload`).

The supplied reference copy is also picked up from `backend/adopt/target_groups.py`
when no file exists directly in `backend/`. The current seed has 51 core and 338
marketing entries, giving 367 unique groups after case-insensitive dedupe.

Alternatively, save `data/groups_seed.json`:

```json
{
  "core": ["My Group A", {"name": "My Group B", "link": "https://chat.whatsapp.com/..."}],
  "marketing": ["Target Group 1", "Target Group 2"],
  "categories": {"business": ["Target Group 1"], "property": ["Target Group 2"]},
  "links": {"My Group A": "https://chat.whatsapp.com/..."}
}
```

The seeder removes duplicates case-insensitively (core wins), fills region from the
group name or an explicit `region`, classifies the topic, sets `n = 1`, and marks core
groups as both core and "my groups". Existing UI edits are never overwritten; only
empty fields are filled.

## Seeding products

The supplied exports live in `backend/adopt/products/` (`wa_products.json`,
`instagram_posts.json`, `linkedin_posts.json`). They are local/adoption files and
are ignored by git. Import them from the Products page with **Seed products**, or:

```bash
cd backend
.\venv\Scripts\python.exe seed_products.py            # import
.\venv\Scripts\python.exe seed_products.py --dry-run  # report only
```

Options:

- `--preserve-status` — keep the 24 Instagram items the source marks as posted
  (by default Instagram items are imported as **Not posted**, because "posted"
  there means Instagram, not WhatsApp).
- `--all-pending` — import every product as **Not posted**, including WhatsApp
  products the source marks as posted.
- `path ...` — JSON files or folders to read instead of the default directory.

Mapping: `link` is the source URL, WhatsApp names keep `product_name` verbatim,
Instagram items are named `Instagram Reel <id>` / `Instagram Post <id>`, category
is `whatsapp` or `instagram`, and `media_url` stays empty. WhatsApp `posted`
items get `posted_at`/`last_posted_at` from the source date and time.
`description` is only filled from a non-empty Instagram caption (the current
exports have none). Scheduling fields are ignored; campaigns own scheduling.

Seeding is idempotent: products are matched by exact link (no URL normalisation),
existing rows are never overwritten or deleted, and only blank name/description/
category/media-url fields are filled. Invalid/non-http links are skipped with a
warning. The API equivalent is `POST /admin/seed-products` (optional query flags
`dry_run`, `preserve_status`, `all_pending`). Nothing is seeded automatically at
startup, so products deleted in the UI stay deleted.

## Campaigns

- Kinds: product → group(s), product → client(s), or my-group link → group(s).
- Targets: one group/client, **several selected clients**, one or more reusable group
  batches, or every active group/client.
- **Group batches** are named, reusable presets managed on the Groups page. A batch is a
  live link, not a snapshot: every campaign that selects it resolves the current member
  groups at run time, so editing a batch changes all campaigns that use it on their next
  run. A campaign may select several batches; duplicate groups are counted once, and
  inactive or currently capped groups are filtered out at run time. A batch can be
  deleted only after it has been removed from every campaign.
- All-target and group-batch campaigns post in batches of `batch_size` and keep looping
  inside the same run until the whole cycle is covered; the cursor resets only at cycle
  end, so nobody is skipped or repeated early. `BATCH_PAUSE_SECONDS` (default 5) paces the
  gaps between batches. The existing single-group and all-groups scopes are unchanged.
- Repeat daily / weekly / monthly at a chosen day and time. Busy slots push forward to
  the next free slot; a manual early run keeps the scheduled slot. Cancel works while a
  run is in progress.

## API

`http://127.0.0.1:8000/docs` while the server is running.

Routes: `/health`, `/version`, `/products`, `/groups`, `/group-batches`, `/clients`,
`/campaigns`, `/schedules`, `/analytics`, `/logs`, `/upload` (+ `/uploads/*`),
`/admin/seed-groups` (+ `/admin/seed-groups/upload`), `/admin/seed-products`.

## Disclaimer
For educational purposes only. Comply with WhatsApp's Terms of Service. Use a test WhatsApp account, never your primary number.
