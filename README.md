# Marketing Bot

WhatsApp marketing automation bot built with Python + Playwright, served through a
FastAPI backend with a React + TypeScript dashboard.

## Stack
- **Backend:** Python 3.12+, FastAPI, Playwright (headless Chromium), pydantic, SQLite, python-dotenv
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, axios

## Quick start

Backend:
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
playwright install chromium
python -m uvicorn main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` for the dashboard and `http://localhost:8000/docs` for the API.

## Disclaimer
For educational purposes only. Comply with WhatsApp's Terms of Service. Use a test WhatsApp account, never your primary number.
