from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, Response
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import threading
import os
import sys
import socket
import time
import webbrowser
import shutil
import json
import uuid
from pathlib import Path
import uvicorn

from db_logic import init_db, log, logs, get_conn, query, execute
from bot import reports
from config import DB_PATH, API_HOST, API_PORT, UPLOAD_DIR
from bot import (
    WhatsAppBot, stop_bot, run_campaign, cancel_campaign, try_claim_campaign,
    is_any_campaign_running, get_busy_recommendation,
    check_schedule_conflicts, run_due_schedules, due_campaigns,
    sync_all_campaigns, defer_campaign,
    reset_products_if_all_posted,
    session_qr, show_browser, use_headless, use_headed,
)
from bot import run_state
from bot import settings as app_settings
from bot import maintenance
from bot.live_state import get_connection_state
from bot.campaign_runner import (
    get_max_group_misses,
    preview_remaining,
    set_max_group_misses,
    session_status,
    reset_session,
)
from scheduling import (
    sync_campaign_schedule, set_campaign_pending_product, refresh_pending_products,
    parse_dt, fmt_dt,
)
from seed_groups import maybe_seed_groups, seed_groups, SEED_JSON
from seed_products import seed_products
from models import (
    Product, ProductInput, ProductStatusUpdate, Group, GroupInput, Client, ClientInput,
    Feedback, FeedbackInput, FeedbackUpdate,
    Campaign, CampaignInput, GroupBatch, GroupBatchBase, ClientBatch, ClientBatchBase,
    Schedule, ScheduleBase, LogEntry,
    LiveDbPayload, LiveDbHealth, LiveDbFlow, LiveDbStepFailure, LiveDbEvent, LiveDbRun,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log("info", "api started", "api")
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    playwright_dir = os.path.join(base_dir, "ms-playwright")
    if os.path.isdir(playwright_dir):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", playwright_dir)
    sync_all_campaigns()
    maybe_seed_groups()
    try:
        # Short-lived hosts and first-run installs still benefit: this only
        # deletes operational history older than the retention window.
        maintenance.maybe_retention_cleanup(
            app_settings.get_int("retention_days", 30),
            min_interval_hours=app_settings.get_int("retention_interval_hours", 24),
        )
    except Exception as exc:
        log("error", f"startup retention cleanup failed: {exc}", "maintenance")
    start_scheduler()
    yield
    _scheduler_stop.set()
    stop_bot()


app = FastAPI(title="Marketing Bot API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded media is always served, whether or not the UI is built yet.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

_bot: Optional[WhatsAppBot] = None
_bot_lock = threading.Lock()
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()


def _frontend_dist() -> Path:
    """Locate frontend/dist in a source checkout and in a packaged build."""
    candidates: List[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "frontend" / "dist")
    candidates.append(Path(__file__).resolve().parent.parent / "frontend" / "dist")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


FRONTEND_DIST = _frontend_dist()


@app.get("/version")
def version():
    return {"version": "0.3.0", "status": "ok"}


def start_scheduler():
    global _scheduler_thread
    if os.getenv("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        return
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()

    def loop():
        while not _scheduler_stop.is_set():
            try:
                run_due_schedules()
            except Exception as e:
                log("error", f"scheduler tick error: {e}", "scheduler")
            try:
                maintenance.maybe_retention_cleanup(
                    app_settings.get_int("retention_days", 30),
                    min_interval_hours=app_settings.get_int("retention_interval_hours", 24),
                )
            except Exception as e:
                log("error", f"retention cleanup error: {e}", "maintenance")
            try:
                reports.maybe_generate_weekly()
            except Exception as e:
                log("error", f"weekly market report failed: {e}", "reports")
            _scheduler_stop.wait(max(1, app_settings.get_int("scheduler_tick_seconds", 5)))

    _scheduler_thread = threading.Thread(target=loop, daemon=True)
    _scheduler_thread.start()


@app.get("/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}


# ── logs ────────────────────────────────────────────────────────────────
@app.get("/logs", response_model=List[LogEntry])
def get_logs(limit: int = 50):
    return logs(limit)


# ── products ────────────────────────────────────────────────────────────
@app.get("/products", response_model=List[Product])
def list_products():
    return query("SELECT * FROM products ORDER BY id DESC")


@app.post("/products", response_model=Product)
def create_product(p: ProductInput):
    pid = execute(
        "INSERT INTO products (name, description, media_url, link, category, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'isNotPosted', datetime('now'))",
        (p.name, p.description, p.media_url, p.link, p.category),
    )
    row = query("SELECT * FROM products WHERE id = ?", (pid,))
    return row[0] if row else {**p.dict(), "id": pid, "status": "isNotPosted"}


@app.patch("/products/{pid}", response_model=Product)
def update_product(pid: int, p: ProductInput):
    execute(
        "UPDATE products SET name = ?, description = ?, media_url = ?, link = ?, category = ?, "
        "status = ?, updated_at = datetime('now') WHERE id = ?",
        (p.name, p.description, p.media_url, p.link, p.category, p.status, pid),
    )
    row = query("SELECT * FROM products WHERE id = ?", (pid,))
    if not row:
        raise HTTPException(status_code=404, detail="product not found")
    return row[0]


@app.delete("/products/{pid}")
def delete_product(pid: int):
    execute("DELETE FROM products WHERE id = ?", (pid,))
    return {"deleted": pid}


@app.patch("/products/{pid}/status")
def update_product_status(pid: int, payload: ProductStatusUpdate):
    conn = get_conn()
    conn.execute(
        "UPDATE products SET status = ?, "
        "posted_at = CASE WHEN ? = 'isPosted' THEN datetime('now') ELSE posted_at END "
        "WHERE id = ?",
        (payload.status, payload.status, pid),
    )
    conn.commit()
    conn.close()
    return {"id": pid, "status": payload.status}


@app.post("/products/reset-all")
def reset_all_products():
    reset_products_if_all_posted()
    return {"reset": True}


# ── groups ──────────────────────────────────────────────────────────────
@app.get("/groups", response_model=List[Group])
def list_groups():
    return query("SELECT * FROM groups ORDER BY id DESC")


@app.post("/groups", response_model=Group)
def create_group(g: GroupInput):
    gid = execute(
        "INSERT INTO groups (name, category, location, n, link, is_my_group, is_core) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (g.name, g.category, g.location, max(1, g.n), g.link,
         1 if g.is_my_group else 0, 1 if g.is_core else 0),
    )
    row = query("SELECT * FROM groups WHERE id = ?", (gid,))
    return row[0] if row else {**g.dict(), "id": gid}


@app.patch("/groups/{gid}")
def update_group(gid: int, g: GroupInput):
    execute(
        "UPDATE groups SET name = ?, category = ?, location = ?, n = ?, link = ?, "
        "is_my_group = ?, is_core = ? WHERE id = ?",
        (g.name, g.category, g.location, max(1, g.n), g.link,
         1 if g.is_my_group else 0, 1 if g.is_core else 0, gid),
    )
    return {"id": gid}


@app.patch("/groups/{gid}/active")
def set_group_active(gid: int, payload: dict):
    execute("UPDATE groups SET is_active = ? WHERE id = ?", (1 if payload.get("is_active") else 0, gid))
    return {"id": gid, "is_active": bool(payload.get("is_active"))}


@app.post("/groups/{gid}/unsilence")
def unsilence_group(gid: int):
    rows = query("SELECT * FROM groups WHERE id = ?", (gid,))
    if not rows:
        raise HTTPException(status_code=404, detail="group not found")
    execute(
        "UPDATE groups SET is_silenced = 0, failures = 0, silenced_at = NULL, "
        "silence_reason = NULL WHERE id = ?",
        (gid,),
    )
    log("info", f"group '{rows[0].get('name')}' unsilenced; it is eligible again", "api")
    updated = query("SELECT * FROM groups WHERE id = ?", (gid,))
    return updated[0] if updated else {"id": gid}


@app.delete("/groups/{gid}")
def delete_group(gid: int):
    # Keep live batch presets accurate: a deleted group cannot remain a member.
    execute("DELETE FROM group_batch_members WHERE group_id = ?", (gid,))
    execute("DELETE FROM groups WHERE id = ?", (gid,))
    return {"deleted": gid}


# ── clients ─────────────────────────────────────────────────────────────
@app.get("/clients", response_model=List[Client])
def list_clients():
    return query("SELECT * FROM clients ORDER BY id DESC")


@app.post("/clients", response_model=Client)
def create_client(c: ClientInput):
    cid = execute(
        "INSERT INTO clients (name, number, category, location, birthdays) VALUES (?, ?, ?, ?, ?)",
        (c.name, c.number, c.category, c.location, c.birthdays),
    )
    row = query("SELECT * FROM clients WHERE id = ?", (cid,))
    return row[0] if row else {**c.dict(), "id": cid}


@app.patch("/clients/{cid}")
def update_client(cid: int, c: ClientInput):
    execute(
        "UPDATE clients SET name = ?, number = ?, category = ?, location = ?, birthdays = ? WHERE id = ?",
        (c.name, c.number, c.category, c.location, c.birthdays, cid),
    )
    return {"id": cid}


@app.delete("/clients/{cid}")
def delete_client(cid: int):
    execute("DELETE FROM clients WHERE id = ?", (cid,))
    return {"deleted": cid}


# ── batches (shared core for groups and clients) ────────────────────────
_BATCH_KINDS: Dict[str, Dict[str, str]] = {
    "group": {
        "batch_table": "group_batches",
        "member_table": "group_batch_members",
        "member_ref": "group_id",
        "base_table": "groups",
        "base_ref": "group_id",
        "ids_field": "group_ids",
        "label": "group",
    },
    "client": {
        "batch_table": "client_batches",
        "member_table": "client_batch_members",
        "member_ref": "client_id",
        "base_table": "clients",
        "base_ref": "client_id",
        "ids_field": "client_ids",
        "label": "client",
    },
}


def _kind_cfg(kind: str) -> Dict[str, str]:
    cfg = _BATCH_KINDS.get(kind)
    if not cfg:
        raise HTTPException(status_code=500, detail=f"unknown batch kind '{kind}'")
    return cfg


def _batch_member_ids(kind: str, batch_id: int) -> List[int]:
    cfg = _kind_cfg(kind)
    return [
        int(r["member"])
        for r in query(
            f"SELECT {cfg['member_ref']} AS member FROM {cfg['member_table']} WHERE batch_id = ? ORDER BY member",
            (batch_id,),
        )
    ]


def _unique_existing_batch_members(kind: str, member_ids) -> List[int]:
    cfg = _kind_cfg(kind)
    existing = {int(r["id"]) for r in query(f"SELECT id FROM {cfg['base_table']}")}
    result: List[int] = []
    seen = set()
    for raw in member_ids or []:
        try:
            member_id = int(raw)
        except (TypeError, ValueError):
            continue
        if member_id in seen:
            continue
        seen.add(member_id)
        if member_id in existing:
            result.append(member_id)
    return result


def _save_batch_members(kind: str, batch_id: int, member_ids) -> None:
    cfg = _kind_cfg(kind)
    execute(f"DELETE FROM {cfg['member_table']} WHERE batch_id = ?", (batch_id,))
    for member_id in _unique_existing_batch_members(kind, member_ids):
        execute(
            f"INSERT OR IGNORE INTO {cfg['member_table']} (batch_id, {cfg['member_ref']}) VALUES (?, ?)",
            (batch_id, member_id),
        )


def _batch_name_taken(kind: str, name: str, exclude_id: Optional[int] = None) -> bool:
    cfg = _kind_cfg(kind)
    rows = query(
        f"SELECT id FROM {cfg['batch_table']} WHERE lower(trim(name)) = lower(trim(?))",
        (name,),
    )
    if exclude_id is None:
        return bool(rows)
    return any(int(r["id"]) != int(exclude_id) for r in rows)


def _get_batch(kind: str, batch_id: int) -> Optional[dict]:
    if kind == "group":
        rows = query(
            "SELECT b.*, "
            "(SELECT COUNT(*) FROM group_batch_members m WHERE m.batch_id = b.id) AS group_count, "
            "(SELECT COUNT(DISTINCT cgb.campaign_id) FROM campaign_group_batches cgb "
            " WHERE cgb.batch_id = b.id) AS campaign_count "
            "FROM group_batches b WHERE b.id = ?",
            (batch_id,),
        )
        if not rows:
            return None
        row = rows[0]
        row["group_ids"] = _batch_member_ids(kind, batch_id)
        return row
    rows = query(
        "SELECT b.*, "
        "(SELECT COUNT(*) FROM client_batch_members m WHERE m.batch_id = b.id) AS client_count, "
        "0 AS use_count "
        "FROM client_batches b WHERE b.id = ?",
        (batch_id,),
    )
    if not rows:
        return None
    row = rows[0]
    row["client_ids"] = _batch_member_ids(kind, batch_id)
    return row


def _validate_batch_payload_core(kind: str, base, exclude_id: Optional[int] = None) -> tuple[str, List[int]]:
    cfg = _kind_cfg(kind)
    label = cfg["label"]
    name = (getattr(base, "name", "") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"{label} batch name is required")
    if _batch_name_taken(kind, name, exclude_id):
        raise HTTPException(status_code=400, detail=f"a {label} batch with that name already exists")
    member_ids = _unique_existing_batch_members(kind, getattr(base, cfg["ids_field"], None))
    if not member_ids:
        raise HTTPException(status_code=400, detail=f"select at least one {label}")
    return name, member_ids


@app.get("/group-batches", response_model=List[GroupBatch])
def list_group_batches():
    rows = query(_batch_list_sql("group"))
    for row in rows:
        row["group_ids"] = _batch_member_ids("group", row["id"])
    return rows


@app.get("/client-batches", response_model=List[ClientBatch])
def list_client_batches():
    rows = query(_batch_list_sql("client"))
    for row in rows:
        row["client_ids"] = _batch_member_ids("client", row["id"])
    return rows


def _batch_list_sql(kind: str) -> str:
    if kind == "group":
        return (
            "SELECT b.*, "
            "(SELECT COUNT(*) FROM group_batch_members m WHERE m.batch_id = b.id) AS group_count, "
            "(SELECT COUNT(DISTINCT cgb.campaign_id) FROM campaign_group_batches cgb "
            " WHERE cgb.batch_id = b.id) AS campaign_count "
            "FROM group_batches b ORDER BY b.id DESC"
        )
    return (
        "SELECT b.*, "
        "(SELECT COUNT(*) FROM client_batch_members m WHERE m.batch_id = b.id) AS client_count, "
        "0 AS use_count "
        "FROM client_batches b ORDER BY b.id DESC"
    )


@app.post("/group-batches", response_model=GroupBatch)
def create_group_batch(b: GroupBatchBase):
    name, group_ids = _validate_batch_payload_core("group", b)
    bid = execute(
        "INSERT INTO group_batches (name, description, created_at) "
        "VALUES (?, ?, datetime('now'))",
        (name, (b.description or "").strip() or None),
    )
    _save_batch_members("group", bid, group_ids)
    row = _get_batch("group", bid)
    if row:
        return row
    raise HTTPException(status_code=400, detail="could not create group batch")


@app.post("/client-batches", response_model=ClientBatch)
def create_client_batch(b: ClientBatchBase):
    name, client_ids = _validate_batch_payload_core("client", b)
    bid = execute(
        "INSERT INTO client_batches (name, description, created_at) "
        "VALUES (?, ?, datetime('now'))",
        (name, (b.description or "").strip() or None),
    )
    _save_batch_members("client", bid, client_ids)
    row = _get_batch("client", bid)
    if row:
        return row
    raise HTTPException(status_code=400, detail="could not create client batch")


@app.patch("/group-batches/{batch_id}", response_model=GroupBatch)
def update_group_batch(batch_id: int, b: GroupBatchBase):
    if not _get_batch("group", batch_id):
        raise HTTPException(status_code=404, detail="group batch not found")
    name, group_ids = _validate_batch_payload_core("group", b, exclude_id=batch_id)
    execute(
        "UPDATE group_batches SET name = ?, description = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (name, (b.description or "").strip() or None, batch_id),
    )
    _save_batch_members("group", batch_id, group_ids)
    row = _get_batch("group", batch_id)
    if row:
        return row
    raise HTTPException(status_code=404, detail="group batch not found")


@app.patch("/client-batches/{batch_id}", response_model=ClientBatch)
def update_client_batch(batch_id: int, b: ClientBatchBase):
    if not _get_batch("client", batch_id):
        raise HTTPException(status_code=404, detail="client batch not found")
    name, client_ids = _validate_batch_payload_core("client", b, exclude_id=batch_id)
    execute(
        "UPDATE client_batches SET name = ?, description = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (name, (b.description or "").strip() or None, batch_id),
    )
    _save_batch_members("client", batch_id, client_ids)
    row = _get_batch("client", batch_id)
    if row:
        return row
    raise HTTPException(status_code=404, detail="client batch not found")


@app.delete("/group-batches/{batch_id}")
def delete_group_batch(batch_id: int):
    if not _get_batch("group", batch_id):
        raise HTTPException(status_code=404, detail="group batch not found")
    used = query(
        "SELECT COUNT(DISTINCT campaign_id) AS c FROM campaign_group_batches WHERE batch_id = ?",
        (batch_id,),
    )
    count = int(used[0]["c"] if used else 0)
    if count:
        raise HTTPException(
            status_code=409,
            detail=f"This batch is used by {count} campaign(s); remove it from those campaigns first.",
        )
    execute("DELETE FROM group_batch_members WHERE batch_id = ?", (batch_id,))
    execute("DELETE FROM group_batches WHERE id = ?", (batch_id,))
    return {"deleted": batch_id}


@app.delete("/client-batches/{batch_id}")
def delete_client_batch(batch_id: int):
    if not _get_batch("client", batch_id):
        raise HTTPException(status_code=404, detail="client batch not found")
    # Client batches are not referenced by campaigns yet, so no referential guard is needed.
    execute("DELETE FROM client_batch_members WHERE batch_id = ?", (batch_id,))
    execute("DELETE FROM client_batches WHERE id = ?", (batch_id,))
    return {"deleted": batch_id}


# ── campaigns ───────────────────────────────────────────────────────────
def _campaign_client_ids(campaign_id: int) -> List[int]:
    return [
        r["client_id"]
        for r in query(
            "SELECT client_id FROM campaign_clients WHERE campaign_id = ? ORDER BY client_id",
            (campaign_id,),
        )
    ]


def _save_campaign_clients(campaign_id: int, client_ids) -> None:
    execute("DELETE FROM campaign_clients WHERE campaign_id = ?", (campaign_id,))
    seen = set()
    for client_id in client_ids or []:
        try:
            client_id = int(client_id)
        except (TypeError, ValueError):
            continue
        if client_id in seen:
            continue
        seen.add(client_id)
        execute(
            "INSERT OR IGNORE INTO campaign_clients (campaign_id, client_id) VALUES (?, ?)",
            (campaign_id, client_id),
        )


def _requested_client_ids(c: CampaignInput) -> List[int]:
    if c.campaign_type != "product_client":
        return []
    if c.client_ids is not None:
        return [int(x) for x in c.client_ids if x is not None]
    return [c.client_id] if c.client_id else []


def _campaign_batch_ids(campaign_id: int) -> List[int]:
    return [
        r["batch_id"]
        for r in query(
            "SELECT batch_id FROM campaign_group_batches WHERE campaign_id = ? ORDER BY batch_id",
            (campaign_id,),
        )
    ]


def _save_campaign_batches(campaign_id: int, batch_ids) -> None:
    execute("DELETE FROM campaign_group_batches WHERE campaign_id = ?", (campaign_id,))
    seen = set()
    for raw in batch_ids or []:
        try:
            batch_id = int(raw)
        except (TypeError, ValueError):
            continue
        if batch_id in seen:
            continue
        seen.add(batch_id)
        execute(
            "INSERT OR IGNORE INTO campaign_group_batches (campaign_id, batch_id) VALUES (?, ?)",
            (campaign_id, batch_id),
        )


def _requested_batch_ids(c: CampaignInput, scope: str) -> List[int]:
    if c.campaign_type != "product_group" or scope != "batch":
        return []
    result: List[int] = []
    seen = set()
    for raw in c.batch_ids or []:
        if raw is None:
            continue
        batch_id = int(raw)
        if batch_id in seen:
            continue
        seen.add(batch_id)
        result.append(batch_id)
    return result


def _validate_batch_ids(batch_ids: List[int]) -> None:
    if not batch_ids:
        raise HTTPException(status_code=400, detail="select at least one group batch")
    existing = {r["id"] for r in query("SELECT id FROM group_batches")}
    if any(batch_id not in existing for batch_id in batch_ids):
        raise HTTPException(status_code=400, detail="one or more group batches were not found")


@app.get("/campaigns", response_model=List[Campaign])
def list_campaigns():
    rows = query("SELECT * FROM campaigns ORDER BY id DESC")
    for row in rows:
        row["client_ids"] = _campaign_client_ids(row["id"])
        row["batch_ids"] = _campaign_batch_ids(row["id"])
    return rows


@app.post("/campaigns", response_model=Campaign)
def create_campaign(c: CampaignInput):
    if c.campaign_type not in ("product_group", "product_client", "myGroupLink"):
        raise HTTPException(status_code=400, detail="unknown campaign type")
    scheduled = _normalise_time(c.scheduled_time) if c.scheduled_time else None
    frequency = (c.frequency or "").lower() or None
    if c.repeatPost and frequency not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="repeat campaigns need a daily/weekly/monthly frequency")
    client_ids = _requested_client_ids(c)
    if c.campaign_type == "product_client" and c.target_scope != "all" and not client_ids:
        raise HTTPException(status_code=400, detail="select at least one client")
    # Link campaigns always move through all eligible target groups; they never
    # use a single fixed group and never pick a product.
    scope = "all" if c.campaign_type == "myGroupLink" else (c.target_scope or "single")
    batch_ids = _requested_batch_ids(c, scope)
    if c.campaign_type == "product_group" and scope == "batch":
        _validate_batch_ids(batch_ids)
    auto_product = 0 if c.campaign_type == "myGroupLink" else (1 if c.auto_product else 0)
    group_id = None if scope == "batch" else c.group_id
    cid = execute(
        "INSERT INTO campaigns (name, campaign_type, product_id, group_id, client_id, my_group_link, "
        "scheduled_time, status, rePost, repeatPost, frequency, repeat_day, repeat_time, "
        "target_scope, auto_product, batch_size, duration_minutes, capture_replies, capture_dwell_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'isScheduledFor', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            c.name, c.campaign_type, c.product_id, group_id,
            client_ids[0] if len(client_ids) == 1 else None,
            c.my_group_link,
            scheduled, 1 if c.rePost else 0, 1 if c.repeatPost else 0, frequency,
            c.repeat_day, c.repeat_time, scope,
            auto_product, max(0, c.batch_size), max(5, c.duration_minutes),
            1 if c.capture_replies else 0, max(0, min(600, int(c.capture_dwell_seconds or 0))),
        ),
    )
    _save_campaign_clients(cid, client_ids)
    _save_campaign_batches(cid, batch_ids)
    # A changed target scope/batch size starts a fresh coverage cycle.
    execute(
        "DELETE FROM app_meta WHERE key IN (?, ?, ?)",
        (
            f"campaign:{cid}:group_cursor",
            f"campaign:{cid}:client_cursor",
            f"campaign:{cid}:link_cursor",
        ),
    )
    sync_campaign_schedule(cid)
    set_campaign_pending_product(cid)
    refresh_pending_products()
    row = query("SELECT * FROM campaigns WHERE id = ?", (cid,))
    if row:
        row[0]["client_ids"] = client_ids
        row[0]["batch_ids"] = batch_ids
        return row[0]
    return {
        **c.dict(), "id": cid, "status": "isScheduledFor", "posts_sent": 0,
        "client_ids": client_ids, "batch_ids": batch_ids,
    }


@app.patch("/campaigns/{cid}")
def update_campaign(cid: int, c: CampaignInput):
    scheduled = _normalise_time(c.scheduled_time) if c.scheduled_time else None
    frequency = (c.frequency or "").lower() or None
    if c.repeatPost and frequency not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="repeat campaigns need a daily/weekly/monthly frequency")
    client_ids = _requested_client_ids(c)
    if c.campaign_type == "product_client" and c.target_scope != "all" and not client_ids:
        raise HTTPException(status_code=400, detail="select at least one client")
    scope = "all" if c.campaign_type == "myGroupLink" else (c.target_scope or "single")
    batch_ids = _requested_batch_ids(c, scope)
    if c.campaign_type == "product_group" and scope == "batch":
        _validate_batch_ids(batch_ids)
    auto_product = 0 if c.campaign_type == "myGroupLink" else (1 if c.auto_product else 0)
    group_id = None if scope == "batch" else c.group_id
    execute(
        "UPDATE campaigns SET name = ?, campaign_type = ?, product_id = ?, group_id = ?, "
        "client_id = ?, my_group_link = ?, scheduled_time = ?, rePost = ?, repeatPost = ?, "
        "frequency = ?, repeat_day = ?, repeat_time = ?, target_scope = ?, auto_product = ?, "
        "batch_size = ?, duration_minutes = ?, capture_replies = ?, capture_dwell_seconds = ? WHERE id = ?",
        (
            c.name, c.campaign_type, c.product_id, group_id,
            client_ids[0] if len(client_ids) == 1 else None,
            c.my_group_link,
            scheduled, 1 if c.rePost else 0, 1 if c.repeatPost else 0, frequency,
            c.repeat_day, c.repeat_time, scope,
            auto_product, max(0, c.batch_size), max(5, c.duration_minutes),
            1 if c.capture_replies else 0, max(0, min(600, int(c.capture_dwell_seconds or 0))), cid,
        ),
    )
    _save_campaign_clients(cid, client_ids)
    _save_campaign_batches(cid, batch_ids)
    # A changed target scope/batch size starts a fresh coverage cycle.
    execute(
        "DELETE FROM app_meta WHERE key IN (?, ?, ?)",
        (
            f"campaign:{cid}:group_cursor",
            f"campaign:{cid}:client_cursor",
            f"campaign:{cid}:link_cursor",
        ),
    )
    sync_campaign_schedule(cid)
    set_campaign_pending_product(cid)
    refresh_pending_products()
    return {"id": cid, "client_ids": client_ids, "batch_ids": batch_ids}


@app.delete("/campaigns/{cid}")
def delete_campaign(cid: int):
    cancel_campaign(cid)
    stop_bot()
    execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
    execute("DELETE FROM campaign_clients WHERE campaign_id = ?", (cid,))
    execute("DELETE FROM campaign_group_batches WHERE campaign_id = ?", (cid,))
    execute("DELETE FROM campaign_posts WHERE campaign_id = ?", (cid,))
    execute(
        "DELETE FROM app_meta WHERE key IN (?, ?, ?)",
        (
            f"campaign:{cid}:group_cursor",
            f"campaign:{cid}:client_cursor",
            f"campaign:{cid}:link_cursor",
        ),
    )
    execute("DELETE FROM campaigns WHERE id = ?", (cid,))
    refresh_pending_products()
    return {"deleted": cid}


@app.post("/campaigns/{cid}/start")
def start_campaign(cid: int, background: BackgroundTasks):
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign = dict(row)
    if campaign["status"] == "isRunning":
        return {"id": cid, "status": "isRunning", "message": "already running"}
    if not try_claim_campaign(cid):
        when = defer_campaign(cid)
        return {
            "id": cid,
            "status": "isBusy",
            "message": f"Another campaign is running. This campaign was moved to the next free slot: {when}.",
            "next_run_at": when,
        }
    background.add_task(run_campaign, cid)
    return {"id": cid, "status": "isRunning"}


@app.post("/campaigns/{cid}/stop")
def stop_campaign(cid: int):
    # Cooperative cancel + hard kill: the runner notices the event for its
    # bookkeeping, and force_kill_browser_processes tears down Chromium
    # immediately instead of waiting on a graceful close.
    cancel_campaign(cid)
    stop_bot()
    return {"id": cid, "status": "isPosted", "message": "stopping"}


@app.post("/campaigns/{cid}/cancel")
def cancel_campaign_endpoint(cid: int):
    cancel_campaign(cid)
    stop_bot()
    return {"id": cid, "status": "isPosted", "message": "cancelled"}


@app.get("/campaigns/{cid}/busy")
def campaign_busy(cid: int):
    return {"id": cid, "busy": is_any_campaign_running(), "recommendation": get_busy_recommendation()}


@app.post("/admin/kill-server")
def kill_server():
    """Terminate the bot and shut down the backend process.

    Responds first, then kills browser processes and exits. The dashboard
    shows a stopped screen; only the desktop shortcut can start it again.
    """
    def _die():
        time.sleep(0.5)
        try:
            stop_bot()
        except Exception:
            pass
        os._exit(0)

    threading.Thread(target=_die, daemon=True).start()
    return {"ok": True, "message": "Marketing Bot server is shutting down."}


# ── feedback (bug reports / suggestions) ────────────────────────────────
_ALLOWED_SCREENSHOT_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _feedback_row(row: dict) -> dict:
    data = dict(row)
    try:
        data["screenshots"] = json.loads(data.get("screenshots") or "[]")
    except Exception:
        data["screenshots"] = []
    data.setdefault("status", "new")
    return data


@app.get("/feedback", response_model=List[Feedback])
def list_feedback(status: Optional[str] = None):
    sql = "SELECT * FROM feedback"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status.strip().lower(),)
    sql += " ORDER BY id DESC"
    return [_feedback_row(r) for r in query(sql, params)]


@app.post("/feedback", response_model=Feedback)
def create_feedback(payload: FeedbackInput):
    fid = execute(
        "INSERT INTO feedback (type, severity, title, description, steps, expected, actual, recommended, screenshots, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')",
        (
            payload.type,
            payload.severity,
            payload.title,
            payload.description,
            payload.steps,
            payload.expected,
            payload.actual,
            payload.recommended,
            json.dumps(payload.screenshots),
        ),
    )
    rows = query("SELECT * FROM feedback WHERE id = ?", (fid,))
    if not rows:
        raise HTTPException(status_code=500, detail="feedback was not persisted")
    return _feedback_row(rows[0])


@app.put("/feedback/{fid}")
def replace_feedback(fid: int, payload: FeedbackInput):
    rows = query("SELECT id FROM feedback WHERE id = ?", (fid,))
    if not rows:
        raise HTTPException(status_code=404, detail="feedback not found")
    execute(
        "UPDATE feedback SET type = ?, severity = ?, title = ?, description = ?, "
        "steps = ?, expected = ?, actual = ?, recommended = ?, screenshots = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (
            payload.type,
            payload.severity,
            payload.title,
            payload.description,
            payload.steps,
            payload.expected,
            payload.actual,
            payload.recommended,
            json.dumps(payload.screenshots),
            fid,
        ),
    )
    return _feedback_row(query("SELECT * FROM feedback WHERE id = ?", (fid,))[0])


@app.patch("/feedback/{fid}", response_model=Feedback)
def update_feedback(fid: int, payload: FeedbackUpdate):
    rows = query("SELECT id FROM feedback WHERE id = ?", (fid,))
    if not rows:
        raise HTTPException(status_code=404, detail="feedback not found")
    execute(
        "UPDATE feedback SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (payload.status, fid),
    )
    return _feedback_row(query("SELECT * FROM feedback WHERE id = ?", (fid,))[0])


@app.delete("/feedback/{fid}")
def delete_feedback(fid: int):
    execute("DELETE FROM feedback WHERE id = ?", (fid,))
    return {"deleted": fid}


@app.post("/feedback/screenshot")
async def upload_feedback_screenshot(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_SCREENSHOT_EXT:
        raise HTTPException(status_code=400, detail="Only image files (png, jpg, jpeg, gif, webp, bmp) are allowed")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    safe = f"feedback_{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / safe
    size = 0
    with dest.open("wb") as buffer:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > 8 * 1024 * 1024:
                buffer.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Screenshot exceeds 8 MB")
            buffer.write(chunk)
    return {"media_url": f"/uploads/{safe}"}


# ── market reports / capture review ─────────────────────────────────────
_VALID_INTENTS = (
    "price", "availability", "order", "location", "delivery",
    "complaint", "compliment", "greeting", "other", "unclassified",
)


@app.get("/market/reports")
def list_market_reports(limit: int = 50):
    return reports.list_reports(limit)


@app.post("/market/reports")
def create_market_report(payload: Optional[dict] = None):
    payload = payload or {}
    title = str(payload.get("title") or "").strip() or None
    try:
        days = max(1, min(3650, int(payload.get("days", 7))))
    except (TypeError, ValueError):
        days = 7
    campaign_id = payload.get("campaign_id")
    try:
        campaign_id = int(campaign_id) if campaign_id not in (None, "", "all") else None
    except (TypeError, ValueError):
        campaign_id = None
    report = reports.create_report(title, days=days, trigger="manual", campaign_id=campaign_id)
    if not report:
        raise HTTPException(status_code=500, detail="report was not persisted")
    return report


@app.get("/market/reports/{rid}")
def get_market_report(rid: int):
    report = reports.get_report(rid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@app.delete("/market/reports/{rid}")
def delete_market_report(rid: int):
    if not reports.delete_report(rid):
        raise HTTPException(status_code=404, detail="report not found")
    return {"deleted": rid}


@app.get("/market/reports/{rid}/markdown")
def market_report_markdown(rid: int):
    report = reports.get_report(rid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return PlainTextResponse(
        reports.markdown_of(report),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=market-report-{rid}.md"},
    )


@app.get("/market/reports/{rid}/csv")
def market_report_csv(rid: int):
    report = reports.get_report(rid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return PlainTextResponse(
        reports.csv_of(report),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=market-report-{rid}.csv"},
    )


@app.get("/market/reports/{rid}/pdf")
def market_report_pdf(rid: int):
    report = reports.get_report(rid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    try:
        pdf = reports.pdf_of(report)
    except Exception as exc:
        log("error", f"market report {rid} PDF render failed: {exc}", "reports")
        raise HTTPException(status_code=500, detail="PDF rendering failed")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=market-report-{rid}.pdf"},
    )


@app.get("/market/review")
def market_review_queue(limit: int = 50):
    limit = max(1, min(200, int(limit or 50)))
    return query(
        "SELECT m.id, m.group_id, g.name AS group_name, m.sender, m.text, "
        "       m.captured_at, m.intent, m.sentiment, m.topics "
        "FROM group_messages m LEFT JOIN groups g ON g.id = m.group_id "
        "WHERE m.spam_flag = 1 AND m.reviewed = 0 "
        "ORDER BY m.captured_at DESC LIMIT ?",
        (limit,),
    )


@app.post("/market/review/{mid}")
def market_review_message(mid: int, payload: dict):
    action = str((payload or {}).get("action") or "").lower()
    if action == "spam":
        execute("UPDATE group_messages SET spam_flag = 1, reviewed = 1 WHERE id = ?", (mid,))
    elif action == "clean":
        execute("UPDATE group_messages SET spam_flag = 0, reviewed = 1 WHERE id = ?", (mid,))
    elif action == "keep":
        execute("UPDATE group_messages SET reviewed = 1 WHERE id = ?", (mid,))
    else:
        raise HTTPException(status_code=400, detail="action must be spam|clean|keep")
    return {"ok": True}


@app.get("/market/unclassified")
def market_unclassified_queue(limit: int = 50):
    limit = max(1, min(200, int(limit or 50)))
    return query(
        "SELECT m.id, m.group_id, g.name AS group_name, m.sender, m.text, "
        "       m.captured_at, m.intent, m.sentiment, m.topics "
        "FROM group_messages m LEFT JOIN groups g ON g.id = m.group_id "
        "WHERE m.intent = 'unclassified' AND m.reviewed = 0 "
        "ORDER BY m.captured_at DESC LIMIT ?",
        (limit,),
    )


@app.post("/market/classify/{mid}")
def market_classify_message(mid: int, payload: dict):
    intent = str((payload or {}).get("intent") or "").lower()
    if intent not in _VALID_INTENTS:
        raise HTTPException(status_code=400, detail=f"intent must be one of {', '.join(_VALID_INTENTS)}")
    execute("UPDATE group_messages SET intent = ?, reviewed = 1 WHERE id = ?", (intent, mid))
    return {"ok": True}


@app.get("/market/vault")
def market_vault_list():
    return query(
        "SELECT v.id, v.normalized_link, v.source, v.group_id, g.name AS group_name, "
        "       v.first_seen, v.last_seen, v.seen_count "
        "FROM group_link_vault v LEFT JOIN groups g ON g.id = v.group_id "
        "ORDER BY v.last_seen DESC LIMIT 200"
    )


@app.delete("/market/vault/{vid}")
def market_vault_delete(vid: int):
    execute("DELETE FROM group_link_vault WHERE id = ?", (vid,))
    return {"deleted": vid}


# ── live run state ──────────────────────────────────────────────────────
def _parse_run_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _elapsed_seconds(started_at: Optional[str], finished_at: Optional[str] = None) -> Optional[int]:
    start = _parse_run_dt(started_at)
    if not start:
        return None
    end = _parse_run_dt(finished_at) or datetime.now()
    return max(0, int((end - start).total_seconds()))


def _product_payload(run: dict) -> Optional[dict]:
    pid = run.get("product_id")
    name = run.get("product_name")
    if not pid and not name:
        return None
    payload = {"id": pid, "name": name, "link": None, "has_media": False}
    if pid:
        rows = query("SELECT link, media_url FROM products WHERE id = ?", (pid,))
        if rows:
            payload["link"] = rows[0].get("link")
            payload["has_media"] = bool(rows[0].get("media_url"))
    return payload


def _current_target_payload(run: dict) -> Optional[dict]:
    run_id = run.get("id")
    row = None
    if run_id and run.get("current_target_id") is not None:
        rows = query(
            "SELECT * FROM campaign_run_targets WHERE run_id = ? AND target_type = ? AND target_id = ?",
            (run_id, run.get("target_type") or "group", run["current_target_id"]),
        )
        row = rows[0] if rows else None
    if row is None and run_id:
        rows = query(
            "SELECT * FROM campaign_run_targets WHERE run_id = ? AND status = 'current' "
            "ORDER BY id DESC LIMIT 1",
            (run_id,),
        )
        row = rows[0] if rows else None
    if row is None and run.get("current_target_name"):
        row = {
            "target_type": run.get("target_type"),
            "target_id": run.get("current_target_id"),
            "target_name": run.get("current_target_name"),
            "attempts": 0,
            "message": None,
            "source_name": None,
            "status": "current",
        }
    if not row:
        return None
    payload = {
        "type": row.get("target_type"),
        "id": row.get("target_id"),
        "name": row.get("target_name"),
        "source_name": row.get("source_name"),
        "attempts": row.get("attempts") or 0,
        "message": row.get("message"),
        "status": row.get("status"),
    }
    if payload["type"] == "group" and payload["id"]:
        groups = query(
            "SELECT failures, total_misses, isPostedProductToday, n, is_silenced FROM groups WHERE id = ?",
            (payload["id"],),
        )
        if groups:
            g = groups[0]
            payload.update(
                failures=g.get("failures") or 0,
                total_misses=g.get("total_misses") or 0,
                daily_count=g.get("isPostedProductToday") or 0,
                daily_cap=g.get("n") or 1,
                is_silenced=bool(g.get("is_silenced")),
            )
    return payload


def _run_payload(run: dict, include_preview: bool = True) -> dict:
    product = _product_payload(run)
    preview_count = 0
    if include_preview:
        campaigns = query("SELECT * FROM campaigns WHERE id = ?", (run["campaign_id"],))
        if campaigns:
            try:
                preview_count = len(preview_remaining(campaigns[0], run_id=run["id"]))
            except Exception:
                preview_count = 0
    counts = {
        "total": int(run.get("total_targets") or 0),
        "processed": int(run.get("processed") or 0),
        "sent": int(run.get("sent") or 0),
        "failed": int(run.get("failed") or 0),
        "skipped": int(run.get("skipped") or 0),
        "remaining": int(run.get("remaining") or 0),
        "preview": preview_count,
    }
    payload = {
        "id": run["id"],
        "campaign_id": run["campaign_id"],
        "campaign_name": run.get("campaign_name"),
        "campaign_type": run.get("campaign_type"),
        "status": run.get("status"),
        "phase": run.get("phase"),
        "product": product,
        "source": product if run.get("campaign_type") == "myGroupLink" else None,
        "current_target": _current_target_payload(run),
        "counts": counts,
        "skip_requested": bool(run.get("skip_requested")),
        "cycle_complete": bool(run.get("cycle_complete")),
        "error": run.get("error"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "last_update": run.get("last_update"),
        "elapsed_seconds": _elapsed_seconds(run.get("started_at"), run.get("finished_at")),
    }
    return payload


@app.get("/live/connection")
def live_connection():
    return get_connection_state()


@app.get("/live/active")
def live_active():
    connection = get_connection_state()
    run = run_state.get_active_run()
    if not run:
        recent = run_state.list_runs(limit=1)
        last_payload = _run_payload(recent[0]) if recent else None
        return {
            "active": False,
            "run": None,
            "last_run": last_payload,
            "connection": connection,
        }
    return {
        "active": True,
        "run": _run_payload(run),
        "last_run": None,
        "connection": connection,
    }


@app.get("/live/runs")
def live_runs(limit: int = 20, campaign_id: Optional[int] = None):
    return [_run_payload(run) for run in run_state.list_runs(limit=limit, campaign_id=campaign_id)]


@app.get("/live/runs/{run_id}")
def live_run_detail(run_id: int):
    run = run_state.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run": _run_payload(run),
        "targets": run_state.list_run_targets(run_id),
        "events": run_state.list_run_events(run_id, limit=200),
    }


@app.get("/live/runs/{run_id}/targets")
def live_run_targets(run_id: int, status: Optional[str] = None):
    if not run_state.get_run(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return run_state.list_run_targets(run_id, status=status)


@app.get("/live/runs/{run_id}/events")
def live_run_events(run_id: int, after_id: int = 0, limit: int = 200):
    if not run_state.get_run(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return run_state.list_run_events(run_id, after_id=after_id, limit=limit)


@app.get("/live/campaigns/{cid}/remaining")
def live_campaign_remaining(cid: int):
    campaigns = query("SELECT * FROM campaigns WHERE id = ?", (cid,))
    if not campaigns:
        raise HTTPException(status_code=404, detail="campaign not found")
    run = run_state.get_active_run(campaign_id=cid)
    run_id = run["id"] if run else None
    current = run_state.list_run_targets(run_id, status="pending,current") if run_id else []
    preview = preview_remaining(campaigns[0], run_id=run_id)
    return {
        "campaign_id": cid,
        "run_id": run_id,
        "current": current,
        "preview": preview,
        "total": len(current) + len(preview),
    }


# ── live dataflow payload ───────────────────────────────────────────────
# Contract for GET /live/db (v = 1):
# { v, ts, pools[], flows[], events[], runs{}, steps[], db{}, scheduler_tick_seconds }
# - pools: health probes with id/label/status/percent/detail (relative load)
# - flows: one entry per latest run with sent rate in the last 60s
# - events: the latest 25 run events (oldest first, ring-buffer cap on client)
# - steps: failure counts grouped by the step=... token from TARGET FAILED lines
# - db: raw counts and the sqlite file size
# Unknown keys are ignored by clients; missing optional keys default. v mismatch
# means a compat notice, never an exception.
ACTIVE_RUN_STATUSES = (
    "starting",
    "running",
    "paused",
    "waiting_login",
    "waiting_qr",
    "reconnecting",
)


def _fmt_bytes_live(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


@app.get("/live/db", response_model=LiveDbPayload)
def get_live_db():
    # App-wide convention: SQLite datetime('now') is UTC. Match it, or rate windows skew.
    cutoff_60 = (datetime.utcnow() - timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")

    rows = query("SELECT * FROM campaign_runs ORDER BY id DESC LIMIT 1")
    latest = rows[0] if rows else None
    is_active = bool(latest) and str(latest.get("status") or "") in ACTIVE_RUN_STATUSES

    run_id = int(latest["id"]) if latest else None
    sent_1m = (
        int(query(
            "SELECT COUNT(*) AS c FROM campaign_run_events WHERE run_id = ? "
            "AND message LIKE ? AND created_at >= ?",
            (run_id, "%MESSAGE SENT SUCCESSFULLY%", cutoff_60),
        )[0]["c"])
        if run_id
        else 0
    )
    failed_1m = (
        int(query(
            "SELECT COUNT(*) AS c FROM campaign_run_events WHERE run_id = ? "
            "AND message LIKE ? AND created_at >= ?",
            (run_id, "%TARGET FAILED%", cutoff_60),
        )[0]["c"])
        if run_id
        else 0
    )
    events_rate = (
        int(query(
            "SELECT COUNT(*) AS c FROM campaign_run_events WHERE run_id = ? AND created_at >= ?",
            (run_id, cutoff_60),
        )[0]["c"])
        if run_id
        else 0
    )
    logs_1m = int(query(
        "SELECT COUNT(*) AS c FROM logs WHERE created_at >= ?",
        (cutoff_60,),
    )[0]["c"])

    total = int(latest.get("total_targets") or 0) if latest else 0
    processed = int(latest.get("processed") or 0) if latest else 0
    sent = int(latest.get("sent") or 0) if latest else 0
    failed = int(latest.get("failed") or 0) if latest else 0
    skipped = int(latest.get("skipped") or 0) if latest else 0
    remaining = int(latest.get("remaining") or 0) if latest else 0
    preview = 0
    if latest:
        try:
            campaigns = query("SELECT * FROM campaigns WHERE id = ?", (latest["campaign_id"],))
            if campaigns:
                preview = len(preview_remaining(campaigns[0], run_id=latest["id"]))
        except Exception:
            preview = 0

    state = get_connection_state()
    conn_state = state.get("state") or "unknown"
    if conn_state == "connected":
        wa = ("ok", 100.0, "WhatsApp session is connected")
    elif conn_state in ("waiting_qr", "waiting_login"):
        wa = ("warning", 40.0, "WhatsApp is waiting for a QR scan or re-login")
    elif conn_state in ("disconnected", "error"):
        wa = ("critical", 0.0, f"WhatsApp is not usable ({conn_state})")
    elif conn_state == "reconnecting":
        wa = ("warning", 30.0, "WhatsApp is reconnecting")
    elif conn_state in ("launching", "loading"):
        wa = ("warning", 60.0, "WhatsApp is loading")
    else:
        wa = ("idle", 10.0, "No WhatsApp browser is running")

    if is_active and total > 0:
        pct = round(100.0 * remaining / total, 1)
        q_status = "critical" if pct >= 90 else "warning" if pct >= 50 else "ok"
        q_detail = f"{remaining} of {total} targets still queued"
    elif is_active:
        pct = 100.0
        q_status = "warning"
        q_detail = "run reported no targets yet"
    else:
        pct = 0.0
        q_status = "ok"
        q_detail = "no run is in progress"

    step_rows = []
    if run_id:
        raw_steps = query(
            "SELECT message FROM campaign_run_events WHERE run_id = ? "
            "AND message LIKE ? ORDER BY id DESC LIMIT 500",
            (run_id, "%TARGET FAILED | step=%"),
        )
        counts: Dict[str, int] = {}
        for row in raw_steps:
            message = str(row["message"])
            marker = "step="
            pos = message.find(marker)
            if pos == -1:
                continue
            step = message[pos + len(marker):].split(" ", 1)[0].strip(" |")
            if not step:
                continue
            counts[step] = counts.get(step, 0) + 1
        step_rows = [
            LiveDbStepFailure(step=step, count=count)
            for step, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]

    try:
        db_bytes = int(os.path.getsize(DB_PATH))
    except OSError:
        db_bytes = 0

    def _count(sql: str) -> int:
        return int(query(sql)[0]["c"])

    pools = [
        LiveDbHealth(id="whatsapp", label="WhatsApp session", status=wa[0], percent=wa[1], detail=wa[2]),
        LiveDbHealth(id="run_queue", label="Active run queue", status=q_status, percent=pct, detail=q_detail),
        LiveDbHealth(
            id="writes",
            label="Log write rate",
            status="ok" if logs_1m <= 60 else "warning",
            percent=float(min(100, logs_1m)),
            detail=f"{logs_1m} log line(s) in the last 60s",
        ),
        LiveDbHealth(
            id="db_size",
            label="SQLite database",
            status="ok",
            percent=0.0,
            detail=_fmt_bytes_live(db_bytes),
        ),
    ]

    flows: List[LiveDbFlow] = []
    if latest:
        run_status = str(latest.get("status") or "idle")
        flows.append(
            LiveDbFlow(
                id="run",
                label=str(latest.get("campaign_name") or f"Run #{latest['id']}"),
                sent_per_min=float(sent_1m),
                failed_1m=failed_1m,
                total=total,
                processed=processed,
                status=run_status,
            )
        )

    events: List[LiveDbEvent] = []
    if run_id:
        raw_events = query(
            "SELECT id, level, event_type, message, created_at "
            "FROM campaign_run_events WHERE run_id = ? ORDER BY id DESC LIMIT 25",
            (run_id,),
        )
        raw_events = list(reversed(raw_events))
        for row in raw_events:
            events.append(
                LiveDbEvent(
                    id=int(row["id"]) if row.get("id") is not None else None,
                    level=str(row.get("level") or "info"),
                    event_type=str(row.get("event_type") or "progress"),
                    message=str(row.get("message") or ""),
                    created_at=str(row.get("created_at")) if row.get("created_at") else None,
                )
            )

    return LiveDbPayload(
        v=1,
        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pools=pools,
        flows=flows,
        events=events,
        runs=LiveDbRun(
            active=is_active,
            run_id=run_id,
            campaign_name=str(latest.get("campaign_name")) if latest and latest.get("campaign_name") else None,
            status=str(latest.get("status")) if latest else None,
            phase=str(latest.get("phase")) if latest else None,
            total=total,
            processed=processed,
            sent=sent,
            failed=failed,
            skipped=skipped,
            remaining=remaining,
            preview=preview,
        ),
        steps=step_rows,
        db={
            "bytes": db_bytes,
            "log_rows": _count("SELECT COUNT(*) AS c FROM logs"),
            "run_rows": _count("SELECT COUNT(*) AS c FROM campaign_runs"),
            "target_rows": _count("SELECT COUNT(*) AS c FROM campaign_run_targets"),
            "event_rows": _count("SELECT COUNT(*) AS c FROM campaign_run_events"),
            "events_rate_1m": events_rate,
            "logs_rate_1m": logs_1m,
        },
        scheduler_tick_seconds=app_settings.get_int("scheduler_tick_seconds", 5),
    )


@app.post("/campaigns/{cid}/skip-current")
def skip_current_group(cid: int):
    run = run_state.get_active_run(campaign_id=cid)
    if not run:
        raise HTTPException(status_code=409, detail="This campaign is not running.")
    target = _current_target_payload(run)
    if not target:
        raise HTTPException(
            status_code=409,
            detail="There is no current target to skip right now; the runner will pick one up shortly.",
        )
    run_state.request_skip(cid)
    run_state.record_event(
        run["id"],
        "info",
        "progress",
        f"Skip requested for '{target.get('name')}'; it will move to the next target",
        target_type=target.get("type"),
        target_id=target.get("id"),
        target_name=target.get("name"),
        campaign_id=cid,
    )
    return {
        "ok": True,
        "message": "Skip requested; will move to the next group as soon as the current step allows.",
        "run_id": run["id"],
        "target": target,
    }


# ── automation settings ─────────────────────────────────────────────────
@app.get("/settings")
def get_settings():
    return {"values": app_settings.get_values(), "schema": app_settings.get_schema()}


@app.patch("/settings")
def update_settings(payload: dict):
    raw = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(status_code=400, detail="provide at least one setting value")
    try:
        values = app_settings.update_settings(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"values": values, "schema": app_settings.get_schema()}


# ── saved session / QR control ──────────────────────────────────────────
@app.get("/session/status")
def get_session_status():
    return session_status()


@app.post("/session/reset")
def reset_saved_session():
    return reset_session()


@app.get("/session/qr")
def get_session_qr():
    return session_qr()


@app.post("/session/show-browser")
def show_session_browser():
    return show_browser()


@app.post("/session/use-headless")
def use_session_headless():
    return use_headless()


@app.post("/session/use-headed")
def use_session_headed():
    return use_headed()


# ── maintenance ─────────────────────────────────────────────────────────
@app.get("/maintenance/stats")
def get_maintenance_stats():
    return maintenance.stats()


@app.post("/maintenance/clear-logs")
def clear_maintenance_logs():
    return maintenance.clear_logs()


@app.post("/maintenance/clear-runs")
def clear_maintenance_runs():
    return maintenance.clear_finished_runs()


@app.post("/maintenance/clear-debug")
def clear_maintenance_debug():
    return maintenance.clear_debug_files()


@app.post("/maintenance/clear-all")
def clear_maintenance_all():
    return maintenance.clear_all_safe()


@app.post("/maintenance/cleanup-now")
def run_retention_cleanup_now():
    days = app_settings.get_int("retention_days", 30)
    return maintenance.retention_cleanup(days)


# ── schedules ───────────────────────────────────────────────────────────
@app.get("/schedules", response_model=List[Schedule])
def list_schedules():
    return query(
        "SELECT s.*, c.name AS campaign_name, c.frequency AS frequency, c.repeatPost AS repeatPost "
        "FROM schedules s LEFT JOIN campaigns c ON c.id = s.campaign_id "
        "ORDER BY s.start_time"
    )


def _normalise_time(value: str) -> str:
    """Accept both datetime-local ('2026-12-01T09:00') and plain values."""
    return value.replace("T", " ")


@app.post("/schedules", response_model=Schedule)
def create_schedule(s: ScheduleBase):
    start_time = _normalise_time(s.start_time)
    end_time = _normalise_time(s.end_time)
    if not check_schedule_conflicts(start_time, end_time):
        raise HTTPException(status_code=409, detail="time slot overlaps with an existing schedule")
    start = parse_dt(start_time)
    end = parse_dt(end_time)
    if not start or not end or end <= start:
        raise HTTPException(status_code=400, detail="end time must be after start time")
    execute(
        "UPDATE campaigns SET scheduled_time = ?, duration_minutes = ?, next_run_at = ? WHERE id = ?",
        (fmt_dt(start), int((end - start).total_seconds() // 60), fmt_dt(start), s.campaign_id),
    )
    sync_campaign_schedule(s.campaign_id)
    row = query(
        "SELECT s.*, c.name AS campaign_name, c.frequency AS frequency, c.repeatPost AS repeatPost "
        "FROM schedules s LEFT JOIN campaigns c ON c.id = s.campaign_id WHERE s.campaign_id = ?",
        (s.campaign_id,),
    )
    if row:
        return row[0]
    raise HTTPException(status_code=400, detail="could not create schedule")


@app.patch("/schedules/{sid}")
def update_schedule(sid: int, s: ScheduleBase):
    start_time = _normalise_time(s.start_time)
    end_time = _normalise_time(s.end_time)
    if not check_schedule_conflicts(start_time, end_time, exclude_schedule_id=sid):
        raise HTTPException(status_code=409, detail="time slot overlaps with an existing schedule")
    start = parse_dt(start_time)
    end = parse_dt(end_time)
    if not start or not end or end <= start:
        raise HTTPException(status_code=400, detail="end time must be after start time")
    execute(
        "UPDATE campaigns SET scheduled_time = ?, duration_minutes = ?, next_run_at = ? WHERE id = ?",
        (fmt_dt(start), int((end - start).total_seconds() // 60), fmt_dt(start), s.campaign_id),
    )
    sync_campaign_schedule(s.campaign_id)
    return {"id": sid}


@app.delete("/schedules/{sid}")
def delete_schedule(sid: int):
    conn = get_conn()
    row = conn.execute("SELECT campaign_id FROM schedules WHERE id = ?", (sid,)).fetchone()
    conn.close()
    if row:
        execute(
            "UPDATE campaigns SET scheduled_time = NULL, next_run_at = NULL, repeatPost = 0 WHERE id = ?",
            (row["campaign_id"],),
        )
        execute("DELETE FROM schedules WHERE campaign_id = ?", (row["campaign_id"],))
    return {"deleted": sid}


# ── analytics ───────────────────────────────────────────────────────────
@app.get("/analytics")
def get_analytics():
    conn = get_conn()
    total = conn.execute("SELECT COALESCE(SUM(posts_sent), 0) FROM analytics").fetchone()[0]
    groups = conn.execute("SELECT COALESCE(SUM(groups_reached), 0) FROM analytics").fetchone()[0]
    campaigns = conn.execute(
        "SELECT COUNT(DISTINCT campaign_id) FROM campaign_posts WHERE status = 'sent'"
    ).fetchone()[0]
    rows = conn.execute("SELECT * FROM analytics ORDER BY date DESC LIMIT 7").fetchall()
    conn.close()
    return {
        "total_posts": total,
        "total_groups_reached": groups,
        "campaigns_run": campaigns,
        "recent": [dict(r) for r in rows],
    }


# ── group seed import ───────────────────────────────────────────────────
@app.post("/admin/seed-groups")
def run_group_seed():
    return seed_groups()


@app.post("/admin/seed-groups/upload")
async def upload_group_seed(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="seed file must be valid JSON")
    if not (data.get("core") or data.get("marketing")):
        raise HTTPException(status_code=400, detail="seed file needs a non-empty 'core' or 'marketing' list")
    SEED_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return seed_groups()


# ── product seed import ─────────────────────────────────────────────────
@app.post("/admin/seed-products")
def run_product_seed(
    dry_run: bool = False,
    preserve_status: bool = False,
    all_pending: bool = False,
):
    return seed_products(
        dry_run=dry_run,
        preserve_status=preserve_status,
        all_pending=all_pending,
    )


# ── uploads ─────────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    dest = UPLOAD_DIR / Path(file.filename or "upload").name
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"media_url": f"/uploads/{dest.name}"}


# ── UI (single-origin: same server as the API) ─────────────────────────
if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def serve_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")


def set_campaign_status(cid: int, status: str) -> None:
    execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, cid))


def set_campaign_busy(cid: int) -> None:
    set_campaign_status(cid, "isBusy")


def _open_browser():
    time.sleep(3)
    webbrowser.open(f"http://{API_HOST}:{API_PORT}")


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((API_HOST, API_PORT))
    except OSError:
        sock.close()
        # Another instance is already serving; open exactly one new tab.
        webbrowser.open(f"http://{API_HOST}:{API_PORT}")
    else:
        sock.close()
        threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(app, host=API_HOST, port=API_PORT, log_config=None)
