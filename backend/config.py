from dotenv import load_dotenv
import os
import sys
from pathlib import Path

load_dotenv()

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Where the project lives (source checkout) vs. where user data lives.
# When packaged (PyInstaller), keep the writable data outside the install
# folder so a rebuild never creates a second database.
SOURCE_ROOT = Path(__file__).resolve().parent.parent
FROZEN = bool(getattr(sys, "frozen", False))
_default_home = (
    Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "MarketingBot"
    if FROZEN
    else SOURCE_ROOT
)
APP_HOME = Path(os.getenv("MARKETING_HOME", _default_home))

BASE_DIR = SOURCE_ROOT
DATA_DIR = Path(os.getenv("DATA_DIR", APP_HOME / "data"))
SESSION_DIR = Path(os.getenv("WHATSAPP_SESSION_DIR", APP_HOME / "whatsapp_session"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "marketing.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", APP_HOME / "uploads"))

# Resolve relative env paths against APP_HOME so the app behaves the same
# regardless of the current working directory (e.g. launched from backend/).
for _name in ("DATA_DIR", "SESSION_DIR", "DB_PATH", "UPLOAD_DIR"):
    _p = Path(globals()[_name])
    if not _p.is_absolute():
        globals()[_name] = APP_HOME / _p

POST_MIN_DELAY = float(os.getenv("POST_MIN_DELAY", "6"))
POST_MAX_DELAY = float(os.getenv("POST_MAX_DELAY", "15"))
BATCH_PAUSE_SECONDS = float(os.getenv("BATCH_PAUSE_SECONDS", "5"))

# Page-interaction timings, ported from the reference poster's CONFIGURATION
# block. The dashboard settings page can override each one at runtime.
SEARCH_WAIT = float(os.getenv("SEARCH_WAIT", "1"))
OPEN_WAIT = float(os.getenv("OPEN_WAIT", "1"))
FIND_COMPOSE_WAIT = float(os.getenv("FIND_COMPOSE_WAIT", "1"))
AFTER_TYPING_WAIT = float(os.getenv("AFTER_TYPING_WAIT", "1"))
SEND_CONFIRM_WAIT = float(os.getenv("SEND_CONFIRM_WAIT", "1"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "2"))
CONNECTION_CHECK_INTERVAL = int(os.getenv("CONNECTION_CHECK_INTERVAL", "30"))

# ── WhatsApp automation tuning ────────────────────────────────────────
LOGIN_TIMEOUT = int(os.getenv("LOGIN_TIMEOUT", "300"))
CONNECTION_WAIT_TIMEOUT = int(os.getenv("CONNECTION_WAIT_TIMEOUT", "600"))

# Groups are silenced after this many consecutive misses. MAX_GROUP_MISSES is
# the current name; MAX_GROUP_FAILURES is kept as a legacy fallback/alias so
# existing deployments that only set the old variable keep working.
_LEGACY_MAX_GROUP_FAILURES = os.getenv("MAX_GROUP_FAILURES")
MAX_GROUP_MISSES = int(os.getenv("MAX_GROUP_MISSES") or _LEGACY_MAX_GROUP_FAILURES or "10")
MAX_GROUP_FAILURES = int(_LEGACY_MAX_GROUP_FAILURES or MAX_GROUP_MISSES)
LINK_PREVIEW_DELAY = int(os.getenv("LINK_PREVIEW_DELAY", "6"))
TYPING_DELAY_MIN = int(os.getenv("TYPING_DELAY_MIN", "12"))
TYPING_DELAY_MAX = int(os.getenv("TYPING_DELAY_MAX", "28"))

# ── Playwright browsers path ──────────────────────────────────────────
# Point Playwright at the installed Chromium browsers so campaign runs
# launch a visible Chrome window. Falls back to the user's AppData
# ms-playwright install when no env var is provided.
_PLAYWRIGHT_ENV = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
if not _PLAYWRIGHT_ENV:
    _candidates = [
        Path.home() / "AppData" / "Local" / "ms-playwright",
        BASE_DIR / "ms-playwright",
    ]
    for _c in _candidates:
        if _c.exists() and any(_c.iterdir()):
            _PLAYWRIGHT_ENV = str(_c)
            break
if _PLAYWRIGHT_ENV:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _PLAYWRIGHT_ENV
PLAYWRIGHT_BROWSERS_PATH = Path(_PLAYWRIGHT_ENV) if _PLAYWRIGHT_ENV else None

for d in (DATA_DIR, SESSION_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)
