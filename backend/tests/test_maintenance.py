"""Offline checks for maintenance clears and automatic retention.

Runs against a throwaway database/data directory selected through environment
variables. It never touches data/marketing.db, the real WhatsApp session,
Playwright/Chrome or the scheduler.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_maintenance.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_maintenance_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402

db_logic.init_db()

from config import DATA_DIR, DB_PATH, SESSION_DIR  # noqa: E402
from bot import maintenance  # noqa: E402


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def count(table: str) -> int:
    conn = db_logic.get_conn()
    value = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    conn.close()
    return int(value)


def insert(sql: str, params: tuple = ()) -> int:
    conn = db_logic.get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    row_id = int(cur.lastrowid or 0)
    conn.close()
    return row_id


def old_stamp(days: int = 40) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def seed_config() -> dict:
    product_id = insert(
        "INSERT INTO products (name, category, status) VALUES ('Product', 'cat', 'isNotPosted')"
    )
    group_id = insert("INSERT INTO groups (name, category, location) VALUES ('Group', 'cat', 'loc')")
    client_id = insert(
        "INSERT INTO clients (name, number, category, location) VALUES ('Client', '+1234567', 'cat', 'loc')"
    )
    campaign_id = insert(
        "INSERT INTO campaigns (name, campaign_type, product_id, group_id, status) "
        "VALUES ('Campaign', 'product_group', ?, ?, 'isScheduledFor')",
        (product_id, group_id),
    )
    insert(
        "INSERT INTO schedules (campaign_id, start_time, end_time, status) "
        "VALUES (?, '2030-01-01 09:00', '2030-01-01 10:00', 'active')",
        (campaign_id,),
    )
    insert(
        "INSERT INTO analytics (date, posts_sent, groups_reached) VALUES ('2030-01-01', 5, 2)"
    )
    insert(
        "INSERT INTO campaign_posts (campaign_id, target_type, target_id, target_name, status) "
        "VALUES (?, 'group', ?, 'Group', 'sent')",
        (campaign_id, group_id),
    )
    insert(
        "INSERT INTO app_meta (key, value) VALUES ('custom_setting', 'keep-me') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    return {"campaign_id": campaign_id, "group_id": group_id, "client_id": client_id}


def seed_run(campaign_id: int, status: str, *, old: bool = False) -> int:
    started = old_stamp() if old else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    finished = started if status not in maintenance.ACTIVE_RUN_STATUSES else None
    run_id = insert(
        "INSERT INTO campaign_runs (campaign_id, campaign_name, campaign_type, status, "
        "started_at, finished_at, last_update) VALUES (?, 'Campaign', 'product_group', ?, ?, ?, ?)",
        (campaign_id, status, started, finished, started),
    )
    insert(
        "INSERT INTO campaign_run_targets (run_id, campaign_id, target_type, target_id, "
        "target_name, status) VALUES (?, ?, 'group', 1, 'Group', 'sent')",
        (run_id, campaign_id),
    )
    insert(
        "INSERT INTO campaign_run_events (run_id, campaign_id, level, event_type, message, created_at) "
        "VALUES (?, ?, 'info', 'target_sent', 'Target sent', ?)",
        (run_id, campaign_id, started),
    )
    return run_id


def seed_log(message: str, *, old: bool = False) -> None:
    created = old_stamp() if old else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert(
        "INSERT INTO logs (level, message, source, created_at) VALUES ('info', ?, 'test', ?)",
        (message, created),
    )


def seed_debug(name: str, *, old: bool = False) -> Path:
    debug_dir = Path(DATA_DIR) / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / name
    path.write_text("debug", encoding="utf-8")
    if old:
        stamp = time.time() - 40 * 86400
        os.utime(path, (stamp, stamp))
    return path


def reset_runtime() -> None:
    """Reset only test data so each case starts from a clean slate."""
    for table in (
        "campaign_run_events",
        "campaign_run_targets",
        "campaign_runs",
        "logs",
        "campaign_posts",
        "schedules",
        "campaigns",
        "clients",
        "groups",
        "products",
        "analytics",
    ):
        db_logic.execute(f"DELETE FROM {table}")
    for path in (Path(DATA_DIR) / "debug").glob("*"):
        if path.is_file():
            path.unlink()


def test_clear_helpers() -> None:
    reset_runtime()
    ids = seed_config()
    finished = seed_run(ids["campaign_id"], "completed")
    active = seed_run(ids["campaign_id"], "running")
    seed_log("old log", old=True)
    seed_log("new log")
    old_debug = seed_debug("old.png", old=True)
    new_debug = seed_debug("new.png")

    before = maintenance.stats()
    check(before["logs"] == 2, f"unexpected log count {before['logs']}")
    check(before["finished_runs"] == 1, f"unexpected finished count {before}")
    check(before["active_runs"] == 1, f"unexpected active count {before}")
    check(before["debug_files"] == 2, f"unexpected debug count {before}")
    check(before["database_bytes"] > 0, "database size was not reported")

    cleared = maintenance.clear_logs()
    check(cleared["logs"] == 2, f"clear_logs deleted {cleared}")
    check(count("logs") == 1, "clear_logs should leave one audit entry")
    audit = db_logic.query("SELECT * FROM logs")
    check(audit[0]["source"] == "maintenance", f"audit entry missing: {audit}")

    runs = maintenance.clear_finished_runs()
    check(runs["runs"] == 1, f"clear_finished_runs cleared {runs}")
    check(count("campaign_runs") == 1, "active run was deleted")
    check(
        db_logic.query("SELECT * FROM campaign_runs")[0]["id"] == active,
        "the wrong run survived",
    )
    check(count("campaign_run_targets") == 1, "target rows for the active run were lost")
    check(count("campaign_run_events") == 1, "event rows for the active run were lost")
    check(
        db_logic.query("SELECT * FROM campaign_run_targets")[0]["run_id"] == active,
        "finished run target rows were not deleted",
    )
    check(finished != active, "run ids collided")

    debug = maintenance.clear_debug_files()
    check(debug["files"] == 2, f"clear_debug_files cleared {debug}")
    check(not old_debug.exists() and not new_debug.exists(), "debug files survived")
    check(count("products") == 1 and count("clients") == 1, "core data was deleted")
    check(count("analytics") == 1 and count("campaign_posts") == 1, "analytics data was deleted")


def test_clear_all_safe() -> None:
    reset_runtime()
    ids = seed_config()
    active = seed_run(ids["campaign_id"], "running")
    finished_old = seed_run(ids["campaign_id"], "failed", old=True)
    seed_log("one", old=True)
    seed_debug("a.png")
    result = maintenance.clear_all_safe()
    check(result["logs"] >= 1, f"clear all did not clear logs: {result}")
    check(count("logs") == 1, "clear all should leave one audit entry")
    check(count("campaign_runs") == 1, "clear all removed an active run")
    check(db_logic.query("SELECT * FROM campaign_runs")[0]["id"] == active, "wrong run survived")
    check(count("campaign_run_targets") == 1, "clear all touched active target rows")
    check(count("products") == 1, "clear all deleted products")
    check(count("groups") == 1, "clear all deleted groups")
    check(count("clients") == 1, "clear all deleted clients")
    check(count("campaigns") >= 1, "clear all deleted campaigns")
    check(count("schedules") >= 1, "clear all deleted schedules")
    check(count("analytics") == 1, "clear all deleted analytics")
    check(count("campaign_posts") == 1, "clear all deleted campaign posts")
    check(
        db_logic.query("SELECT value FROM app_meta WHERE key = 'custom_setting'")[0]["value"]
        == "keep-me",
        "clear all deleted app settings",
    )
    check(finished_old != active, "run ids collided")

    # Session reset is separate: the session directory must still be untouched.
    marker = Path(SESSION_DIR) / "keep.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("session", encoding="utf-8")
    maintenance.clear_all_safe()
    check(marker.exists(), "clear all touched the WhatsApp session directory")


def test_retention() -> None:
    reset_runtime()
    ids = seed_config()
    old_finished = seed_run(ids["campaign_id"], "completed", old=True)
    new_finished = seed_run(ids["campaign_id"], "completed")
    old_active = seed_run(ids["campaign_id"], "running", old=True)
    seed_log("old log", old=True)
    seed_log("new log")
    old_debug = seed_debug("retention-old.png", old=True)
    new_debug = seed_debug("retention-new.png")

    result = maintenance.retention_cleanup(30)
    check(result["logs"] == 1, f"retention removed the wrong number of logs: {result}")
    check(result["runs"] == 1, f"retention removed the wrong number of runs: {result}")
    check(result["debug_files"] == 1, f"retention removed the wrong debug files: {result}")
    check(result["targets"] == 1 and result["events"] == 1, f"retention targets/events: {result}")

    runs = {row["id"] for row in db_logic.query("SELECT id FROM campaign_runs")}
    check(old_finished not in runs, "old finished run survived retention")
    check(new_finished in runs, "new finished run was deleted")
    check(old_active in runs, "active run was deleted by retention")
    check(count("logs") >= 1, "retention deleted the audit log it just wrote")
    check(old_debug.exists() is False, "old debug file survived retention")
    check(new_debug.exists() is True, "new debug file was deleted")
    check(count("analytics") == 1, "retention deleted analytics")
    check(count("campaign_posts") == 1, "retention deleted campaign posts")
    check(count("products") == 1 and count("groups") == 1 and count("clients") == 1, "retention deleted core data")
    check(count("campaigns") >= 1 and count("schedules") >= 1, "retention deleted configuration")

    last = maintenance.get_last_retention_run()
    check(bool(last), "retention did not record its last run")
    check(maintenance.maybe_retention_cleanup(30) is None, "retention ran twice within 24h")

    check(DB_PATH.exists(), "database disappeared")


def main_test() -> None:
    test_clear_helpers()
    test_clear_all_safe()
    test_retention()
    print("All maintenance/retention tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
