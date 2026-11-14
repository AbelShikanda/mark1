# Live Campaign Dashboard, Skip Control, and Group Silence Plan

## Goal

Make campaign runs observable and controllable from the dashboard instead of relying on the console/log file:

1. Current group being worked on.
2. Current product being posted (or current source group for `myGroupLink`).
3. Missed groups for the active run.
4. Remaining groups for the active run/cycle.
5. A way to skip the current group and move to the next target.
6. Success/failure/progress messages shown live in the UI.
7. Miss counts per group, automatic silencing after the allowed number of misses, and a silenced-group list with edit/delete/unsilence actions.
8. WhatsApp connection state: connected, disconnected, reconnecting, waiting for QR, retry attempt, and recovery.

The reference behaviour lives in:

- `backend/adopt/group_poster.py` — `FailedGroupsTracker`, per-group success/failure tracking, connection checks between steps, posting summary messages.
- `backend/adopt/group_manager.py` — `ensure_connection`, `connection_health_monitor`, connection statistics, pause/resume messages.
- `backend/adopt/login_manager.py` — connected/loading/disconnected/unknown classification, QR markers, reconnect loop.

Do not copy the reference UI or async orchestration wholesale. Port the useful state and failure-tracking ideas into the existing synchronous runner.

---

## Current architecture

- `backend/bot/campaign_runner.py`
  - `run_campaign()` claims a campaign, resolves the product, gets the bot, and runs paced batches.
  - `run_product_group()`, `run_product_client()`, and `run_my_group_link()` loop the selected targets.
  - `record_group_failure()` increments `groups.failures` and currently disables a group at `MAX_GROUP_FAILURES`.
  - `can_post_to_group()` checks `is_active` and the daily cap.
  - `pick_group_batch()` and `_batch()` implement batch pacing and the non-repeating cursor.
- `backend/bot/login_manager.py`
  - `check_connection()` classifies connected/disconnected.
  - `ensure_connection()` waits/loads/reloads and calls `_recover()`.
  - `_wait_for_login()` handles QR registration.
  - Currently only writes generic `logs` rows; no structured live state.
- `backend/bot/poster.py`
  - `post_text()`/`post_image()`/`post_product()` return only `True/False`.
  - Failures are mostly written to `logs` without target context.
- `backend/db_logic.py`
  - `groups` has `failures` and `is_active`.
  - `campaign_posts` records final target results.
  - `logs` is a flat global log.
- `backend/main.py`
  - Campaign start/stop routes exist.
  - No live-run, target-queue, skip, or unsilence endpoints.
- Frontend
  - No Live page.
  - Campaigns page only shows status, next run, and total `posts_sent`.
  - Groups page has Groups and Group batches tabs; no silenced view.

---

## Core semantics

Use these terms consistently:

- **Run**: one execution of a campaign, from `Run now`/scheduler until it finishes or is stopped.
- **Cycle**: one complete pass over the eligible target pool, using the existing cursor behaviour.
- **Target**: one group or client selected for this run.
- **Current target**: the row currently being opened/posted.
- **Pending/remaining**: selected targets not yet attempted in the current chunk, plus a read-only preview of the upcoming cycle chunks.
- **Missed/failed**: a target was attempted but could not be opened or posted, or the post could not be confirmed. This increments the group's miss counter.
- **Skipped**: the user pressed “Skip current”. This is not a failure and must not increment the miss counter.
- **Deferred**: the target was not attempted because it was inactive, silenced, or at its daily cap. This is not a miss.
- **Silenced**: the group reached the allowed miss count and is excluded from future picks until manually unsilenced.

Important decisions:

- A skipped target is skipped for this run only. It remains eligible in a future cycle unless the user disables/silences it.
- A skipped target does **not** count as posted and does **not** count as missed.
- Batch membership is resolved for the run. Editing a batch affects the next run; it does not rewrite the queue already being processed.
- Preserve the existing batch-size/cursor ordering. Do not silently drop groups.
- Keep `is_active` as the manual disable flag. Add a separate `is_silenced` flag so “disabled by user” and “silenced after misses” are distinguishable.
- Default allowed misses should be configurable. Add `MAX_GROUP_MISSES` (default `3`) and keep `MAX_GROUP_FAILURES` as a legacy fallback/alias if it is already set.

---

## Data model

All schema changes must be additive and safe for existing databases via `init_db()`.

### Extend `groups`

Add:

```sql
ALTER TABLE groups ADD COLUMN total_misses INTEGER DEFAULT 0;
ALTER TABLE groups ADD COLUMN is_silenced INTEGER DEFAULT 0;
ALTER TABLE groups ADD COLUMN silenced_at TEXT;
ALTER TABLE groups ADD COLUMN silence_reason TEXT;
ALTER TABLE groups ADD COLUMN last_missed_at TEXT;
ALTER TABLE groups ADD COLUMN last_success_at TEXT;
```

Keep the existing `failures` column as the consecutive-miss counter. `total_misses` is the lifetime count.

Rules:

- `record_group_failure()` increments `failures`, increments `total_misses`, updates `last_missed_at`, and emits a target event.
- When `failures >= MAX_GROUP_MISSES`, set `is_silenced = 1`, `silenced_at`, and `silence_reason`.
- Do not set `is_active = 0` for miss-based silencing anymore.
- `record_group_success()` sets `failures = 0` and updates `last_success_at`; `total_misses` remains.
- `can_post_to_group()` must require `is_active = 1`, `is_silenced = 0`, and daily capacity.
- Group pickers (`_batch_scope_groups`, all-groups picker, link source picker) must exclude silenced groups.

### `campaign_runs`

One row per run:

```sql
CREATE TABLE IF NOT EXISTS campaign_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    campaign_name TEXT,
    campaign_type TEXT,
    status TEXT DEFAULT 'starting',
    phase TEXT DEFAULT 'starting',
    product_id INTEGER,
    product_name TEXT,
    target_type TEXT,
    current_target_id INTEGER,
    current_target_name TEXT,
    total_targets INTEGER DEFAULT 0,
    processed INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    remaining INTEGER DEFAULT 0,
    cycle_complete INTEGER DEFAULT 0,
    skip_requested INTEGER DEFAULT 0,
    error TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    last_update TEXT
);
```

Suggested statuses:

- `starting`, `running`, `paused`, `waiting_login`, `waiting_qr`, `reconnecting`, `completed`, `stopped`, `failed`, `interrupted`.

Suggested phases:

- `resolving_targets`, `batch_starting`, `opening_chat`, `posting`, `verifying`, `waiting_batch`, `finished`.

### `campaign_run_targets`

Rows for targets selected in the current run. This is what the UI uses for current/missed/remaining lists.

```sql
CREATE TABLE IF NOT EXISTS campaign_run_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    campaign_id INTEGER NOT NULL,
    batch_no INTEGER,
    queue_index INTEGER,
    target_type TEXT,
    target_id INTEGER,
    target_name TEXT,
    source_name TEXT,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    message TEXT,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(run_id, target_type, target_id)
);
```

Statuses:

- `pending`, `current`, `sent`, `failed` (shown as “missed”), `skipped`, `deferred`.

Indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_run_targets_run_status
ON campaign_run_targets(run_id, status);
```

### `campaign_run_events`

Structured live feed. This is what replaces “watch the console”.

```sql
CREATE TABLE IF NOT EXISTS campaign_run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    campaign_id INTEGER,
    level TEXT DEFAULT 'info',
    event_type TEXT,
    target_type TEXT,
    target_id INTEGER,
    target_name TEXT,
    message TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

Suggested `event_type` values:

- `run_started`, `batch_started`, `target_opening`, `target_sent`, `target_failed`, `target_skipped`, `target_deferred`, `group_silenced`, `connection_state`, `run_finished`, `error`.

Also write important events to the existing `logs` table so the Logs page remains useful.

### `bot_state`

Single-row connection state:

```sql
CREATE TABLE IF NOT EXISTS bot_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT DEFAULT 'unknown',
    message TEXT,
    attempt INTEGER DEFAULT 0,
    max_attempts INTEGER,
    qr_visible INTEGER DEFAULT 0,
    next_retry_at TEXT,
    updated_at TEXT
);
```

States:

- `unknown`, `launching`, `loading`, `connected`, `disconnected`, `waiting_login`, `waiting_qr`, `reconnecting`, `error`, `stopped`.

---

## Backend implementation

### 1. Add a run-state helper module

Create `backend/bot/run_state.py` (or equivalent) with functions such as:

- `start_run(campaign, product) -> run_id`
- `set_run_phase(run_id, status, phase, message=None)`
- `set_current_target(run_id, target_type, target_id, target_name)`
- `record_target_result(run_id, target, status, message=None)`
- `record_event(run_id, level, event_type, message, target=None)`
- `finish_run(run_id, status, error=None)`
- `request_skip(campaign_id)`
- `consume_skip(campaign_id) -> bool`
- `is_skip_requested(campaign_id) -> bool`

Use a small in-process `threading.Event` map for skip requests, similar to the existing `_cancel_events`, plus the `campaign_runs.skip_requested` DB flag for UI visibility. The runner thread checks the event; the API sets it.

### 2. Create target rows at the start of each batch chunk

Do not rewrite the existing batch/cursor algorithm. In `run_product_group()` / `run_product_client()` / `run_my_group_link()`:

1. Call the existing picker to get the selected batch.
2. Insert `campaign_run_targets` rows for that batch with `status='pending'`.
3. Process each target:
   - set row and run state to `current`;
   - set phase `opening_chat`, then `posting`;
   - on success: row `sent`, increment `sent`;
   - on failure: row `failed`, increment `failed`, increment the group miss counter;
   - on user skip: row `skipped`, increment `skipped`, do not count as failure;
   - on daily cap/inactive/silenced discovery: row `deferred`.
4. Update `processed` and `remaining` after each target.
5. Emit structured events at every step.

Add a read-only remaining preview:

- Extract the pure selection part of `_batch()` so it can simulate the cursor without writing.
- `preview_remaining_groups(campaign)` returns the future chunks after the current cursor.
- The Live UI shows `pending` rows in the current chunk plus this preview. This avoids changing cursor semantics while still showing the whole remaining cycle.
- Do not mutate `app_meta` while previewing.

For `myGroupLink`, store the source group in `campaign_run_targets.source_name` and show it as the “current product/link source”.

### 3. Add skip checks

Add optional callbacks to the poster:

- `post_text(..., on_event=None, should_skip=None)`
- `post_image(..., on_event=None, should_skip=None)`
- `post_product(..., on_event=None, should_skip=None)`

The runner passes callbacks that emit run events and check the skip event.

Check skip:

- before opening the chat;
- after the chat opens and before typing;
- immediately before pressing send.

If skip is requested after the message has actually been sent, let the send finish and mark it sent. The API response should say the skip will apply as soon as the current step allows.

Add a poster progress callback for messages such as:

- opening chat
- chat opened
- typing message
- waiting for link preview
- sending
- sent
- send could not be confirmed
- media attach failed / falling back to text

These become live event-feed entries and also go to `logs`.

### 4. Wire connection state

Create `backend/bot/live_state.py` or put the helper in `run_state.py`:

- `update_connection_state(state, message, attempt=0, max_attempts=None, qr_visible=False, next_retry_at=None)`
- Update the single `bot_state` row.
- If there is an active run, insert a `campaign_run_events` row when the state changes.
- Deduplicate frequent calls; only write when the state/message/attempt changes.

Instrument `WhatsAppBot`:

- `start()` → `launching`
- `navigate()` / `_wait_for_loading()` → `loading`
- `_wait_for_login()` → `waiting_qr` when QR is visible, otherwise `waiting_login`
- `ensure_connection()` failure → `disconnected` / `reconnecting`
- `_recover()` each reload attempt → `reconnecting`, `attempt=N`
- connection success → `connected`
- QR found during recovery → `waiting_qr`
- timeout/error → `error`
- `stop()` → `stopped`

The runner should mark the active run `waiting_qr`/`reconnecting` while `ensure_connection()` is blocked so the UI clearly shows that the campaign is paused, not silently stalled.

### 5. Miss/silence rules

- Increment `failures` for:
  - group could not be found/opened;
  - post failed or could not be confirmed.
- Do not increment for:
  - user skip;
  - daily cap;
  - group already inactive/silenced;
  - connection loss that prevents an attempt (the run is paused; do not blame the group).
- At `failures >= MAX_GROUP_MISSES`:
  - set `is_silenced=1`, `silenced_at`, `silence_reason='auto: N misses'`;
  - emit `group_silenced`;
  - exclude the group immediately from future picks.
- Unsilence:
  - set `is_silenced=0`, `failures=0`, clear `silenced_at`/`silence_reason`;
  - keep `total_misses` for history;
  - emit a log/event.
- Do not delete automatically.

---

## API design

Add routes in `backend/main.py`:

```text
GET  /live/connection
GET  /live/active
GET  /live/runs
GET  /live/runs/{run_id}
GET  /live/runs/{run_id}/targets?status=pending|current|failed|skipped|...
GET  /live/runs/{run_id}/events?after_id=0&limit=200
GET  /live/campaigns/{cid}/remaining
POST /campaigns/{cid}/skip-current
POST /groups/{gid}/unsilence
```

Keep existing `POST /campaigns/{cid}/stop` and `POST /campaigns/{cid}/cancel`.

### `GET /live/active`

Return:

```json
{
  "active": true,
  "run": {
    "id": 12,
    "campaign_id": 3,
    "campaign_name": "Product launch",
    "campaign_type": "product_group",
    "status": "running",
    "phase": "posting",
    "product": {"id": 4, "name": "Shoes"},
    "current_target": {"type": "group", "id": 8, "name": "Buyers"},
    "counts": {
      "total": 120,
      "processed": 45,
      "sent": 42,
      "failed": 1,
      "skipped": 2,
      "remaining": 75
    },
    "started_at": "...",
    "elapsed_seconds": 123
  },
  "connection": {
    "state": "connected",
    "message": "WhatsApp Web connected",
    "attempt": 0,
    "updated_at": "..."
  }
}
```

If no run is active, return `{ "active": false, "last_run": ... }`.

### `POST /campaigns/{cid}/skip-current`

- Set the skip event and the active run's `skip_requested` flag.
- Return 409 if there is no current target for that running campaign.
- Return an acknowledgement such as `{ "ok": true, "message": "Skip requested; will move to the next group." }`.

### `POST /groups/{gid}/unsilence`

- Clear `is_silenced`, `silenced_at`, `silence_reason`, and `failures`.
- Return the updated group.

### Group responses

`GET /groups` should return the new fields automatically:

- `total_misses`
- `is_silenced`
- `silenced_at`
- `silence_reason`
- `last_missed_at`
- `last_success_at`

`PATCH /groups/{gid}` remains the edit endpoint and must not accidentally clear silencing. Deleting a group keeps the existing batch-membership cleanup.

---

## Frontend

### New Live page

Add `frontend/src/pages/LivePage.tsx` and add a `Live` item to `frontend/src/App.tsx` navigation.

Recommended layout:

1. **Connection banner** (always visible)
   - green connected;
   - amber loading/reconnecting;
   - red disconnected/error;
   - blue waiting for QR;
   - show message, attempt number, last update, and “scan QR” guidance.

2. **Run header**
   - campaign name/type;
   - status and phase;
   - product or source group;
   - started/elapsed;
   - progress bar: processed / total.

3. **Current work cards**
   - Current group: name, id, phase, attempt, daily count/cap, miss count.
   - Current product/source: name, link/media presence, posted state.

4. **Counters**
   - total, sent, failed/missed, skipped, remaining, silenced excluded.

5. **Controls**
   - `Skip current group` (confirm; disabled when no current target);
   - `Stop campaign` (confirm; uses existing stop endpoint);
   - `Refresh`.

6. **Tabs/tables**
   - Remaining groups;
   - Missed groups this run (with reason and miss count);
   - All targets;
   - Live events.

7. **Event feed**
   - poll every 1–2 seconds with `after_id`;
   - color by level;
   - auto-scroll only when the user is at the bottom;
   - show timestamps.

Polling is enough for the first version. Avoid adding WebSockets/SSE unless the simple polling version is too slow.

### Campaigns page

- Add a `Live` button for `isRunning` campaigns.
- Optionally show a compact strip above the table when a run is active:
  - current group;
  - current product;
  - sent/remaining;
  - connection state;
  - button to open Live.
- Wire navigation through `App.tsx` with a selected `liveCampaignId`.

### Groups page

Add a third view/tab: **Silenced** (with a count badge).

Silenced table columns:

- group name;
- consecutive misses / allowed threshold;
- total misses;
- last missed;
- silenced at/reason;
- actions: Edit, Unsilence, Delete.

Also show a small badge in the main Groups table when `is_silenced` or `failures > 0`.

Unsilence calls `POST /groups/{gid}/unsilence` and refreshes. Edit should switch to the Groups form with that group loaded. Delete should confirm and then refresh both groups and batches, because deleting a group removes it from batch membership.

### Global connection indicator

Add a small colored dot/status in the sidebar footer or header, polling `/live/connection`. This makes disconnection visible even when the user is not on the Live page.

---

## Implementation order

1. **Schema + models + config**
   - Add columns/tables/indexes.
   - Add models for run/target/event/connection.
   - Add `MAX_GROUP_MISSES` with legacy fallback.
2. **Run-state and connection-state helpers**
   - Add `run_state.py` / `live_state.py`.
   - No runner wiring yet.
3. **Runner instrumentation**
   - Create run rows.
   - Create target rows per chunk.
   - Emit events.
   - Track current target/product/counters/remaining.
4. **Skip support**
   - Add skip events/checkpoints.
   - Add poster callbacks.
5. **Miss/silence behavior**
   - Change `record_group_failure`.
   - Add `is_silenced` filtering.
   - Add unsilence.
6. **API routes**
   - Live endpoints.
   - Skip endpoint.
   - Unsilence endpoint.
7. **Frontend Live page**
   - Polling, banners, cards, tables, event feed, controls.
8. **Campaigns/Groups UI integration**
   - Live button/strip.
   - Silenced tab and actions.
9. **Tests + build**
   - Offline tests.
   - `py_compile`.
   - `npm run build`.

---

## Tests

Create `backend/tests/test_live_run.py` using the same temporary-DB pattern as `test_group_batches.py`:

- `DB_PATH`, `DATA_DIR`, `UPLOAD_DIR`, `WHATSAPP_SESSION_DIR` point to a temp directory.
- `DISABLE_SCHEDULER=1`.
- No WhatsApp, Playwright, Chrome, or real campaign.

Test cases:

1. Run state starts, exposes current target, and finishes with correct counters.
2. Target rows are created for each selected batch and statuses transition correctly.
3. `remaining`/preview reflects the existing cursor and does not mutate it.
4. Skip marks only the current target as `skipped`, does not mark sent/failed, and the next target becomes current.
5. Failed targets increment `failures` and `total_misses`.
6. Silence occurs at the configured threshold and `can_post_to_group()` returns false.
7. Silenced groups are excluded from picks.
8. Unsilence clears silencing and allows the group again.
9. Success resets consecutive `failures` but keeps `total_misses`.
10. Deleting a group removes batch membership (existing behavior).
11. Live API returns active run, targets, events, and connection state.
12. Connection state updates are persisted and readable.
13. Existing group-batch tests still pass.
14. `python -m py_compile` passes for backend files.
15. `npm run build` passes for the frontend.

For runner tests, monkeypatch `get_bot`, `post_product`, and `post_text` with fakes. Do not call the real automation.

---

## Acceptance criteria

- While a campaign is running, the Live page shows the current group, current product/source, phase, counts, remaining list, missed list, and live events.
- Success/failure messages appear in the UI without opening the Logs page or console.
- “Skip current group” moves to the next target; the skipped target is not counted as sent or missed.
- Groups that fail repeatedly show their miss count and become silenced at the allowed threshold.
- Silenced groups are not posted to and appear in the Silenced view.
- Silenced groups can be edited, deleted, or unsilenced; unsilenced groups become eligible again.
- Connection loss shows disconnected/reconnecting/waiting-for-QR state and attempt number; the run visibly pauses and resumes after recovery.
- Existing `product_group`, `product_client`, `myGroupLink`, single/all/batch scope, batch pacing, and cursor behavior are unchanged.
- Tests use a temporary database and never modify `data/marketing.db`.
- No WhatsApp/Chrome launch or real campaign is required for automated tests.
- Frontend build and backend compilation pass.

---

## Copy-paste prompt for a new session

```text
You are working in C:\Users\PRINT SHOP\Desktop\projects\marketing.

Implement the plan in LIVE_RUN_PLAN.md: a live campaign dashboard, skip-current control, structured progress events, group miss counts/silencing, a silenced-groups view, and WhatsApp connection status.

Read these files first:
- backend/bot/campaign_runner.py
- backend/bot/login_manager.py
- backend/bot/poster.py
- backend/db_logic.py
- backend/main.py
- backend/models.py
- backend/config.py
- backend/adopt/group_poster.py
- backend/adopt/group_manager.py
- backend/adopt/login_manager.py
- frontend/src/App.tsx
- frontend/src/pages/CampaignsPage.tsx
- frontend/src/pages/GroupsPage.tsx
- frontend/src/pages/LogsPage.tsx
- frontend/src/api.ts

Key requirements:
1. Show the active campaign's current group and current product (or link source group).
2. Show missed groups, remaining groups, and completed/sent/skipped counters for the active run.
3. Add a Skip current group action that moves to the next target without counting as a sent post or a miss.
4. Show success/failure/progress messages live in the UI, not only in logs/console.
5. Track consecutive and total misses per group. Silence a group at the configured limit (MAX_GROUP_MISSES, default 3, fallback to MAX_GROUP_FAILURES if set) and exclude it from future picks.
6. Add a Silenced groups view where groups can be edited, deleted, or unsilenced.
7. Show WhatsApp connection state: connected, disconnected, reconnecting, waiting for QR, retry attempt, and recovery.
8. Keep existing batch/cursor/scope behavior unchanged. Do not rewrite the batch algorithm unnecessarily.

Implementation notes:
- Add additive schema changes only; use db_logic.init_db() migrations.
- Add campaign_runs, campaign_run_targets, campaign_run_events, and bot_state tables.
- Keep groups.is_active as the manual disable flag; add groups.is_silenced separately.
- A skipped target must not increment failures or total_misses.
- A daily-cap/inactive/silenced target is "deferred", not "missed".
- Create target rows at the start of each selected batch chunk. For remaining, add a read-only preview using the same cursor logic without writing the cursor.
- Add optional callbacks to poster post_text/post_image/post_product for progress events and skip checks.
- Add skip checkpoints before opening chat, after opening, and before sending.
- Instrument login_manager to update bot_state on launch/loading/connected/disconnected/reconnecting/waiting_qr/error.
- Use polling in the UI (1-2 seconds), not WebSockets, unless polling proves insufficient.
- Add a new Live page and nav item; add a Live button/strip to CampaignsPage; add a Silenced tab to GroupsPage; add a global connection indicator if practical.
- Preserve existing product_group, product_client, myGroupLink, single/all/batch scope and cursor semantics.
- Do not modify data/marketing.db. All tests must use a temporary DB_PATH.
- Do not launch WhatsApp/Chrome or run a real campaign. Do not restart or disturb the app at http://127.0.0.1:8000 unless explicitly asked.
- Add tests in backend/tests/test_live_run.py using the temp-DB pattern from backend/tests/test_group_batches.py.
- Run backend py_compile, the existing group-batch tests, and npm run build in frontend.

Deliverables:
- Backend schema/runner/API changes.
- Frontend Live page, Campaigns/Groups integration, connection indicator.
- Tests and build verification.
- A concise final summary of changes and any remaining limitations.
```
