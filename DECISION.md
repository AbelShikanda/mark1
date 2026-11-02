# DECISIONS

## Frontend: React + TypeScript (not TypeScript alone)
React and TypeScript are not alternatives: React is a UI framework typically written in TypeScript. Using React + TS together satisfies all three interview stack requirements (Python backend, TypeScript language, React framework). Pure TypeScript would add no React evidence.

## Backend framework: FastAPI
- In existing skill list (jobsearch config.py STRONG_SKILLS).
- Async-friendly, pairs cleanly with Playwright.
- Ships OpenAPI docs for easy interviewer review.

## Storage: SQLite
- Consistent with jobsearch and waboat; zero-config local dev.

## Frontend tooling: Vite + Tailwind CSS
- Vite is already used in dubairest; Tailwind already configured there.
- Fast to scaffold, small bundle.

## WhatsApp automation: Playwright
- Mirrors waboat exactly (login/session, anti-detection, human-like delays).

## Running both halves
- `concurrently` (already a dep in dubairest) to run API + dev server together.

## Anti-detection
- Carried over from waboat: persistent user-data-dir session, disabled Blink AutomationControlled, random typing/post delays.

## Deferred (not now)
- Other social platforms, auth, multi-user, deployment, billing.
