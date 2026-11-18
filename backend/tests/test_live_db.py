"""Offline test for the /live/db dataflow payload (v=1).

Seeds a throwaway database/session with one finished run and failure events,
then asserts the payload contract the frontend dashboard consumes. It never
touches data/marketing.db and never launches a browser.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_live_db.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_live_db_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402

db_logic.init_db()

import main  # noqa: E402


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def seed_run() -> None:
    conn = db_logic.get_conn()
    cur = conn.execute(
        """INSERT INTO campaign_runs
               (campaign_id, campaign_name, campaign_type, status, phase, total_targets,
                processed, sent, failed, skipped, remaining)
             VALUES (1, 'Dataflow test campaign', 'product_group', 'completed', 'done',
                     5, 5, 3, 2, 0, 0)"""
    )
    run_id = cur.lastrowid
    conn.execute(
        """INSERT INTO campaign_run_events
               (run_id, campaign_id, level, event_type, message, target_name, created_at)
             VALUES (?, 1, 'error', 'progress', '[result] TARGET FAILED | step=read_only | target=Grp A', 'Grp A',
                     datetime('now'))""",
        (run_id,),
    )
    conn.execute(
        """INSERT INTO campaign_run_events
               (run_id, campaign_id, level, event_type, message, target_name, created_at)
             VALUES (?, 1, 'error', 'progress', '[result] TARGET FAILED | step=search | target=Grp B', 'Grp B',
                     datetime('now'))""",
        (run_id,),
    )
    conn.execute(
        """INSERT INTO campaign_run_events
               (run_id, campaign_id, level, event_type, message, target_name, created_at)
             VALUES (?, 1, 'info', 'progress', '[send] MESSAGE SENT SUCCESSFULLY | target=Grp C | elapsed=4.2s', 'Grp C',
                     datetime('now'))""",
        (run_id,),
    )
    conn.commit()
    conn.close()


def main_test() -> None:
    seed_run()

    # The route is registered and the payload round-trips through Pydantic.
    payload = main.get_live_db()
    check(payload.v == 1, f"unexpected payload version {payload.v}")
    check(bool(payload.ts), "payload is missing a timestamp")

    pool_ids = {pool.id for pool in payload.pools}
    check(
        pool_ids == {"whatsapp", "run_queue", "writes", "db_size"},
        f"unexpected pools {pool_ids}",
    )

    check(payload.runs.campaign_name == "Dataflow test campaign", "latest run metadata missing")
    check(payload.runs.run_id is not None and payload.runs.total == 5, "run totals wrong")
    check(payload.runs.sent == 3 and payload.runs.failed == 2, "run sent/failed wrong")
    check(payload.runs.active is False, "finished run reported as active")

    check(len(payload.flows) == 1, "expected exactly one flow for the latest run")
    flow = payload.flows[0]
    check(flow.label == "Dataflow test campaign", "flow label missing")
    check(flow.failed_1m == 2, f"expected 2 failures in the last minute, got {flow.failed_1m}")
    check(flow.sent_per_min == 1, f"expected 1 send in the last minute, got {flow.sent_per_min}")

    steps = {step.step: step.count for step in payload.steps}
    check(steps.get("read_only") == 1, f"read_only failure not parsed: {steps}")
    check(steps.get("search") == 1, f"search failure not parsed: {steps}")

    event_messages = [event.message for event in payload.events]
    check(any("MESSAGE SENT SUCCESSFULLY" in message for message in event_messages), "sent event missing")
    check(any("TARGET FAILED | step=read_only" in message for message in event_messages), "failed event missing")

    check(payload.scheduler_tick_seconds >= 1, "scheduler tick missing")
    check(isinstance(payload.db, dict) and payload.db.get("log_rows", 0) >= 0, "db stats missing")
    check(payload.db.get("log_rows", 0) >= 0, "log row count wrong")

    print("All live db tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
