"""Offline checks for live campaign runs, skip control and group silencing.

Runs against a throwaway database selected through DB_PATH. It never touches
data/marketing.db and never launches WhatsApp, Playwright, Chrome or the
scheduler.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_live_run.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_live_run_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402
from models import CampaignBase, GroupBatchBase  # noqa: E402

db_logic.init_db()
import main  # noqa: E402
from bot import campaign_runner as runner  # noqa: E402
from bot import live_state, run_state  # noqa: E402


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_group(name: str, n: int = 5) -> int:
    conn = db_logic.get_conn()
    cur = conn.execute(
        "INSERT INTO groups (name, n, is_active, isPostedProductToday) VALUES (?, ?, 1, 0)",
        (name, max(1, n)),
    )
    conn.commit()
    group_id = cur.lastrowid
    conn.close()
    return group_id


def get_campaign(cid: int) -> dict:
    rows = db_logic.query("SELECT * FROM campaigns WHERE id = ?", (cid,))
    check(rows, f"campaign {cid} not found")
    return rows[0]


def group_row(gid: int) -> dict:
    rows = db_logic.query("SELECT * FROM groups WHERE id = ?", (gid,))
    check(rows, f"group {gid} not found")
    return rows[0]


class FakeBot:
    """Minimal stand-in for WhatsAppBot; no browser is ever started."""

    def __init__(self) -> None:
        self.cancel_event = None

    def ensure_connection(self, context: str = "test") -> bool:
        return True

    def cancelled(self) -> bool:
        return False

    def human_delay(self) -> None:
        pass


def fake_poster(results):
    """Monkeypatch-friendly poster that follows the optional callbacks."""
    calls: list[str] = []
    queue = list(results)

    def post(bot, target, product, text, context="group", on_event=None, should_skip=None):
        calls.append(target)
        if on_event:
            on_event(f"fake: posting to '{target}'")
        if should_skip and should_skip():
            return False
        if queue:
            return bool(queue.pop(0))
        return True

    return post, calls


def main_test() -> None:
    # ── 1/2. run state + target rows per selected batch chunk ───────────
    g1, g2, g3, g4, g5 = (make_group(f"live-{i}") for i in range(1, 6))
    batch = main.create_group_batch(GroupBatchBase(name="Live batch", group_ids=[g1, g2, g3, g4, g5]))
    campaign = main.create_campaign(
        CampaignBase(
            name="Batch campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[batch["id"]],
            batch_size=2,
        )
    )
    cid = campaign["id"]
    campaign_row = get_campaign(cid)

    run_id = run_state.start_run(campaign_row, {"id": 1, "name": "Widget"})
    run_state.set_run_phase(run_id, status="running", phase="batch_starting")

    product = {"id": 1, "name": "Widget", "description": "desc", "link": "https://example.test"}
    fake, calls = fake_poster([True, True, True, True])
    original_post = runner.post_product
    runner.post_product = fake
    try:
        bot = FakeBot()
        first_sent = runner.run_product_group(campaign_row, product, bot, run_id)
        second_sent = runner.run_product_group(campaign_row, product, bot, run_id)
    finally:
        runner.post_product = original_post

    check(first_sent == 2 and second_sent == 2, f"unexpected sent counts {first_sent}/{second_sent}")
    check(calls == ["live-1", "live-2", "live-3", "live-4"], f"unexpected target order {calls}")

    targets = run_state.list_run_targets(run_id)
    check(len(targets) == 4, f"expected 4 target rows, got {len(targets)}")
    check({t["batch_no"] for t in targets} == {1, 2}, "targets were not grouped into two batches")
    check(all(t["status"] == "sent" for t in targets), "targets did not transition to sent")

    run = run_state.get_run(run_id)
    check(run["total_targets"] == 4, f"total_targets wrong: {run['total_targets']}")
    check(run["sent"] == 4 and run["processed"] == 4, f"counters wrong: {run}")
    check(run["remaining"] == 0, "remaining should be 0 for the selected rows")
    run_state.finish_run(run_id, "completed")
    check(run_state.get_run(run_id)["status"] == "completed", "run did not finish")
    check(run_state.get_active_run() is None, "finished run is still reported active")

    # ── 3. read-only remaining preview keeps the cursor untouched ──────
    cursor_key = f"campaign:{cid}:group_cursor"
    before_cursor = runner._meta_get(cursor_key)
    preview_1 = runner.preview_remaining(campaign_row, run_id=run_id)
    preview_2 = runner.preview_remaining(campaign_row, run_id=run_id)
    check(runner._meta_get(cursor_key) == before_cursor, "preview mutated the batch cursor")
    check([p["target_id"] for p in preview_1] == [g5], f"unexpected preview {preview_1}")
    check(preview_1 == preview_2, "preview is not deterministic")
    # A campaign that has not started previews its whole first cycle.
    fresh = main.create_campaign(
        CampaignBase(
            name="Preview campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[batch["id"]],
            batch_size=2,
        )
    )
    fresh_preview = runner.preview_remaining(get_campaign(fresh["id"]))
    check(
        [p["target_id"] for p in fresh_preview] == [g1, g2, g3, g4, g5],
        f"fresh preview did not cover the cycle: {fresh_preview}",
    )
    check(runner._meta_get(f"campaign:{fresh['id']}:group_cursor") == 0, "fresh preview wrote a cursor")

    # ── 4. skip marks only the current target as skipped ────────────────
    s1, s2 = make_group("skip-1"), make_group("skip-2")
    skip_batch = main.create_group_batch(GroupBatchBase(name="Skip batch", group_ids=[s1, s2]))
    skip_campaign = main.create_campaign(
        CampaignBase(
            name="Skip campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[skip_batch["id"]],
            batch_size=2,
        )
    )
    skip_cid = skip_campaign["id"]
    skip_row = get_campaign(skip_cid)
    skip_run = run_state.start_run(skip_row)
    run_state.request_skip(skip_cid)

    fake, calls = fake_poster([True])
    original_post = runner.post_product
    runner.post_product = fake
    try:
        skip_sent = runner.run_product_group(skip_row, product, FakeBot(), skip_run)
    finally:
        runner.post_product = original_post
    check(skip_sent == 1, f"skip should still send the next target, sent={skip_sent}")
    check(calls == ["skip-2"], f"skipped target was attempted: {calls}")

    skips = run_state.list_run_targets(skip_run)
    by_id = {t["target_id"]: t for t in skips}
    check(by_id[s1]["status"] == "skipped", "first target was not marked skipped")
    check(by_id[s2]["status"] == "sent", "second target was not sent")
    check(group_row(s1)["failures"] == 0, "skip incremented the group miss counter")
    check(run_state.get_run(skip_run)["skipped"] == 1, "skipped counter not updated")
    check(run_state.get_run(skip_run)["failed"] == 0, "skip counted as a failure")
    skip_run_row = run_state.get_run(skip_run)
    check(skip_run_row["current_target_id"] == s2, "current target did not advance after skip")
    run_state.finish_run(skip_run, "completed")

    # ── 5/6/7. misses, silencing and picker exclusion ───────────────────
    runner.MAX_GROUP_MISSES = 3
    m1 = make_group("miss-1")
    for index in range(3):
        silenced = runner.record_group_failure(
            m1, "post failed", run_id=None, campaign_id=cid, target_name="miss-1"
        )
        check(silenced == ("silenced" if index == 2 else "failed"), f"unexpected silence trigger at miss {index + 1}")
    fail_row = group_row(m1)
    check(fail_row["failures"] == 3, f"failures wrong: {fail_row['failures']}")
    check(fail_row["total_misses"] == 3, f"total_misses wrong: {fail_row['total_misses']}")
    check(fail_row["is_silenced"] == 1, "group was not silenced at the threshold")
    check(fail_row["is_active"] == 1, "miss-based silencing must not disable the group")
    check(fail_row["silenced_at"] is not None and fail_row["silence_reason"], "silence metadata missing")
    check(not runner.can_post_to_group(fail_row), "silenced group still passes can_post_to_group")

    m2 = make_group("miss-2")
    miss_batch = main.create_group_batch(GroupBatchBase(name="Miss batch", group_ids=[m1, m2]))
    miss_campaign = main.create_campaign(
        CampaignBase(
            name="Miss campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[miss_batch["id"]],
            batch_size=0,
        )
    )
    miss_row = get_campaign(miss_campaign["id"])
    picked = [g["id"] for g in runner.pick_group_batch(miss_row)]
    check(m1 not in picked, "silenced group was picked")
    check(m2 in picked, "eligible group was dropped alongside the silenced one")

    # ── 8. unsilence clears silencing but keeps lifetime misses ─────────
    updated = main.unsilence_group(m1)
    check(not updated["is_silenced"], "unsilence did not clear is_silenced")
    check(updated["failures"] == 0, "unsilence did not reset consecutive misses")
    check(updated["total_misses"] == 3, "unsilence lost lifetime misses")
    check(updated["silenced_at"] is None and not updated["silence_reason"], "silence metadata not cleared")
    check(runner.can_post_to_group(group_row(m1)), "unsilenced group is still blocked")

    # ── 9. success resets consecutive misses, keeps total ──────────────
    ok_group = make_group("success-1")
    runner.record_group_failure(ok_group, "one")
    runner.record_group_failure(ok_group, "two")
    check(group_row(ok_group)["failures"] == 2, "failures did not increment")
    runner.record_group_success(ok_group)
    success_row = group_row(ok_group)
    check(success_row["failures"] == 0, "success did not reset consecutive failures")
    check(success_row["total_misses"] == 2, "success wiped lifetime misses")
    check(success_row["last_success_at"] is not None, "success timestamp missing")

    # ── 10. deleting a group removes batch membership ──────────────────
    d1 = make_group("delete-1")
    del_batch = main.create_group_batch(GroupBatchBase(name="Delete batch", group_ids=[d1]))
    main.delete_group(d1)
    members = db_logic.query("SELECT * FROM group_batch_members WHERE batch_id = ?", (del_batch["id"],))
    check(not members, "deleting a group left its batch membership behind")

    # ── 11/12. live API + connection state ─────────────────────────────
    api_group = make_group("api-1")
    api_batch = main.create_group_batch(GroupBatchBase(name="API batch", group_ids=[api_group]))
    api_campaign = main.create_campaign(
        CampaignBase(
            name="API campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[api_batch["id"]],
        )
    )
    api_row = get_campaign(api_campaign["id"])
    api_run = run_state.start_run(api_row, {"id": 7, "name": "API product"})
    run_state.set_run_phase(api_run, status="running", phase="posting")
    run_state.create_run_targets(api_run, api_campaign["id"], [{"id": api_group, "name": "api-1"}])
    run_state.set_current_target(api_run, "group", api_group, "api-1", phase="posting")
    run_state.record_target_result(
        api_run, "group", api_group, "sent", "Sent",
        target_name="api-1", campaign_id=api_campaign["id"],
    )

    live_state.update_connection_state("connected", "WhatsApp Web connected")
    connection = main.live_connection()
    check(connection["state"] == "connected", f"connection state not persisted: {connection}")
    check(live_state.get_connection_state()["message"] == "WhatsApp Web connected", "connection message lost")

    active = main.live_active()
    check(active["active"] is True, "live active did not report the run")
    check(active["run"]["id"] == api_run, "live active returned the wrong run")
    check(active["run"]["product"]["name"] == "API product", "live product missing")
    check(active["run"]["counts"]["sent"] == 1, "live counters missing sent count")
    check(active["connection"]["state"] == "connected", "live active connection missing")

    targets = main.live_run_targets(api_run)
    check(any(t["target_id"] == api_group for t in targets), "live targets did not return the target")
    events = main.live_run_events(api_run)
    check(any(e["event_type"] == "target_sent" for e in events), "live events missing target_sent")
    check(any(e["event_type"] == "connection_state" for e in events), "connection state not mirrored to run events")

    remaining = main.live_campaign_remaining(api_campaign["id"])
    check(remaining["run_id"] == api_run, "remaining endpoint did not find the active run")
    check(isinstance(remaining["preview"], list), "remaining preview is not a list")

    # Skip endpoint: only when there is a current target.
    run_state.set_current_target(api_run, "group", api_group, "api-1")
    skip_response = main.skip_current_group(api_campaign["id"])
    check(skip_response["ok"] is True, "skip endpoint did not acknowledge")
    check(run_state.skip_requested(api_campaign["id"]), "skip endpoint did not set the event")
    run_state.clear_skip(api_campaign["id"])
    run_state.finish_run(api_run, "completed")

    try:
        main.skip_current_group(api_campaign["id"])
    except Exception as exc:  # FastAPI HTTPException
        check(getattr(exc, "status_code", None) == 409, f"unexpected skip error {exc}")
    else:
        raise AssertionError("skip endpoint should reject a campaign with no active run")

    last = main.live_active()
    check(last["active"] is False, "finished run still reported active")
    check(last["last_run"] is not None, "last run summary missing")
    check(main.live_connection()["state"] == "connected", "connection state was lost after run finished")

    print("All live run tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
