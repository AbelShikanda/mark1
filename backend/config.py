from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SESSION_DIR = Path(os.getenv("WHATSAPP_SESSION_DIR", "whatsapp_session"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "marketing.db"))

POST_MIN_DELAY = float(os.getenv("POST_MIN_DELAY", "6"))
POST_MAX_DELAY = float(os.getenv("POST_MAX_DELAY", "15"))

for d in (DATA_DIR, SESSION_DIR):
    d.mkdir(parents=True, exist_ok=True)
