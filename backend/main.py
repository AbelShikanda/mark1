from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import json
import threading

from db_logic import init_db, log, logs, get_conn
from config import DB_PATH, API_HOST, API_PORT
from bot import WhatsAppBot, GroupManager, GroupPoster, GroupLinkMarketer, ContactMessenger, AnalyticsModule
from models import Product, ProductBase, Group, GroupBase, Campaign, CampaignBase, LogEntry

app = FastAPI(title="Marketing Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_bot: Optional[WhatsAppBot] = None
_bot_lock = threading.Lock()

from typing import Optional as _Optional  # noqa

# ── lifecycle ───────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    log("info", "api started", "api")

@app.get("/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}

# ── logs ────────────────────────────────────────────────
@app.get("/logs", response_model=List[LogEntry])
def get_logs(limit: int = 50):
    return logs(limit)

# ── products ────────────────────────────────────────────
@app.get("/products", response_model=List[Product])
def list_products():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/products", response_model=Product)
def create_product(p: ProductBase):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO products (name, description, media_url, link, source, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (p.name, p.description, p.media_url, p.link, p.source),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return {**p.dict(), "id": pid, "status": "pending"}

@app.patch("/products/{pid}/status")
def update_product_status(pid: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE products SET status = ?, posted_at = datetime('now') WHERE id = ?", (status, pid))
    conn.commit()
    conn.close()
    return {"id": pid, "status": status}

# ── groups ──────────────────────────────────────────────
@app.get("/groups", response_model=List[Group])
def list_groups():
    mgr = GroupManager(get_conn)
    return mgr.list_groups()

@app.post("/groups", response_model=Group)
def create_group(g: GroupBase):
    mgr = GroupManager(get_conn)
    gid = mgr.add_group(g.name, g.url, g.category)
    return {**g.dict(), "id": gid}

@app.delete("/groups/{gid}")
def delete_group(gid: int):
    mgr = GroupManager(get_conn)
    mgr.remove_group(gid)
    return {"deleted": gid}

# ── campaigns ───────────────────────────────────────────
@app.get("/campaigns", response_model=List[Campaign])
def list_campaigns():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM campaigns ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/campaigns", response_model=Campaign)
def create_campaign(c: CampaignBase):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO campaigns (name, product_ids, group_ids, status) VALUES (?, ?, ?, 'idle')",
        (c.name, json.dumps(c.product_ids), json.dumps(c.group_ids)),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return {**c.dict(), "id": cid, "status": "idle", "posts_sent": 0}

@app.post("/campaigns/{cid}/start")
def start_campaign(cid: int, background: BackgroundTasks):
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="campaign not found")
    conn.execute("UPDATE campaigns SET status = 'running' WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    background.add_task(run_campaign, cid)
    return {"id": cid, "status": "running"}

@app.get("/analytics")
def get_analytics():
    mgr = AnalyticsModule(get_conn)
    return mgr.summary()

# ── background campaign runner ──────────────────────────
def run_campaign(cid: int):
    global _bot
    with _bot_lock:
        if _bot is None:
            _bot = WhatsAppBot(headless=True)
            _bot.start()
    try:
        _bot.navigate()
        conn = get_conn()
        conn.execute("UPDATE campaigns SET status = 'completed', posts_sent = 0 WHERE id = ?", (cid,))
        conn.commit()
        log("info", f"campaign {cid} completed (simulated)", "campaign")
        conn.close()
    except Exception as e:
        conn = get_conn()
        conn.execute("UPDATE campaigns SET status = 'failed' WHERE id = ?", (cid,))
        conn.commit()
        log("error", f"campaign {cid} failed: {e}", "campaign")
        conn.close()
