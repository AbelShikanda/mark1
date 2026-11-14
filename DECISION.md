# DECISIONS

## Frontend: React + TypeScript
React and TypeScript are not alternatives: React is a UI framework typically written in TypeScript. Using React + TS together satisfies all three interview stack requirements (Python backend, TypeScript language, React framework).

## Backend framework: FastAPI
- Async-friendly, pairs cleanly with Playwright.
- Ships OpenAPI docs for easy interviewer review.

## Storage: SQLite
- Zero-config local dev. Schema rebuilt for WhatsApp spec: products, groups, clients, campaigns, schedules, campaign_posts, logs, analytics.

## Frontend tooling: Vite + Tailwind CSS
- Fast to scaffold, small bundle.

## WhatsApp automation: Playwright (headed Chrome)
- Visible Chromium window so the user can see WhatsApp Web in action.
- Persistent user-data-dir session, disabled Blink AutomationControlled, random typing/post delays.
- No cmd shell popup: the desktop shortcut runs `launch-hidden.vbs` → `run.bat`, which builds the frontend and starts the single FastAPI server on :8000. One origin, one database.

## Running it
- End user: Marketing Bot shortcut → builds `frontend/dist`, serves it from FastAPI on `http://127.0.0.1:8000`, opens the browser.
- Dev (optional): `uvicorn --reload` on :8000 + `npm run dev` on :5173 (API base from `.env.development`). The shortcut never uses dev mode.

## WhatsApp business rules (implemented)
- Products: name + link OR image + name OR image + name + link; optional description; category nullable; full edit/update (name, description, link, image, category) and delete without re-creating; status isPosted | isNotPosted | isPending; when every product is posted all are reset to isNotPosted; isPending means "selected by a scheduled campaign, not yet posted" and clears on post; equitable-but-random category rotation; attached images are sent to WhatsApp as an image + caption, not text-only.
- Groups: name + category(nullable) + location(nullable) + n (max posts/day); isPostedProductToday < n else skipped; link nullable; is_my_group marks link sources; is_core marks priority sources and excluded targets for link marketing; failures count disables a group after 100 consecutive failures; enable/disable without deleting.
- Clients/individuals: name + number + category(nullable) + location(nullable) + birthdays(nullable).
- Campaigns: name; product→group(s) OR product→client(s) OR my-group-link→group(s); statuses isPosted | isRunning | isScheduledFor | isBusy; fixed product or auto product (equitable by category); target a single group/client, **one or more selected clients**, or all of them; all-target runs are batched with a cursor and a single run keeps looping the batches until every group/client is covered, so a cycle never stops half-way; rePost allows re-sending an already-posted product; repeatPost is a schedule type (daily / weekly / monthly at a chosen day and time) that keeps running while the app is open; Run now / Run again / Stop / Cancel / Delete; cancel is cooperative and works during a run.
- Scheduling: the **campaign is the source of truth**. Creating or editing a campaign generates its schedule (start + run window); the Schedules page is a read-only reflection with a "Clear schedule" action. Overlapping slots are pushed to the next free slot; a campaign that is due while another is running is moved to the next free slot instead of retrying every few seconds. A manual early run keeps the future scheduled slot.
- Link marketing: sources are only "my groups" that have a link; core groups are prioritised as sources and excluded as targets; links are posted to the campaign's target groups exactly like product posts, with the same daily caps and batch cursor.

## Anti-detection
- Persistent user-data-dir session, disabled Blink AutomationControlled, random typing/post delays.

## Deferred (not now)
- Other social platforms, auth, multi-user, deployment, billing.
