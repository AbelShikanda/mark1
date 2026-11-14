"""Offline checks for reusable group batches.

Runs against a throwaway database selected through DB_PATH. It never touches
data/marketing.db and never launches WhatsApp, Playwright or the scheduler.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_group_batches.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_group_batches_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

from fastapi import HTTPException  # noqa: E402

import db_logic  # noqa: E402
from models import CampaignBase, ClientBase, GroupBatchBase  # noqa: E402
from bot.campaign_runner import (  # noqa: E402
    _batch_scope_groups,
    _cycle_complete,
    _meta_get,
    _meta_set,
    mark_group_posted,
    pick_group_batch,
)

db_logic.init_db()
import main  # noqa: E402


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_http(status: int, fn, message: str) -> None:
    try:
        fn()
    except HTTPException as exc:
        check(exc.status_code == status, f"{message}: expected {status}, got {exc.status_code}")
        return
    raise AssertionError(f"{message}: expected HTTP {status}, no exception raised")


def make_group(name: str, active: bool = True, n: int = 1) -> int:
    conn = db_logic.get_conn()
    cur = conn.execute(
        "INSERT INTO groups (name, n, is_active, isPostedProductToday) VALUES (?, ?, ?, 0)",
        (name, max(1, n), 1 if active else 0),
    )
    conn.commit()
    group_id = cur.lastrowid
    conn.close()
    return group_id


def get_campaign(cid: int) -> dict:
    rows = db_logic.query("SELECT * FROM campaigns WHERE id = ?", (cid,))
    check(rows, f"campaign {cid} not found")
    return rows[0]


def batch_row(batch_id: int) -> dict:
    rows = db_logic.query("SELECT * FROM group_batches WHERE id = ?", (batch_id,))
    check(rows, f"batch {batch_id} not found")
    row = rows[0]
    row["group_ids"] = main._batch_group_ids(batch_id)
    return row


def main_test() -> None:
    # ── group batch CRUD ────────────────────────────────────────────────
    g1, g2, g3, g4 = (make_group(f"crud-{i}") for i in range(1, 5))

    created = main.create_group_batch(
        GroupBatchBase(name="Alpha batch", description="first", group_ids=[g1, g2, g3, g2, 999999])
    )
    check(created["name"] == "Alpha batch", "batch name not saved")
    check(created["group_ids"] == [g1, g2, g3], f"unexpected group_ids {created['group_ids']}")
    check(created["group_count"] == 3, "group_count wrong")

    listed = main.list_group_batches()
    listed_row = next(b for b in listed if b["id"] == created["id"])
    check(listed_row["group_ids"] == [g1, g2, g3], "GET did not return exact group_ids")

    expect_http(
        400,
        lambda: main.create_group_batch(GroupBatchBase(name="  alpha BATCH  ", group_ids=[g1])),
        "duplicate name (case-insensitive)",
    )
    expect_http(
        400,
        lambda: main.create_group_batch(GroupBatchBase(name="Empty batch", group_ids=[])),
        "empty group list",
    )
    expect_http(
        400,
        lambda: main.create_group_batch(GroupBatchBase(name="No real groups", group_ids=[999999])),
        "only non-existent group ids",
    )

    updated = main.update_group_batch(
        created["id"],
        GroupBatchBase(name="Alpha batch", description="updated", group_ids=[g2, g3, g4]),
    )
    check(updated["group_ids"] == [g2, g3, g4], f"update membership failed: {updated['group_ids']}")
    check(updated["updated_at"] is not None, "updated_at not set")

    # ── campaign targeting ──────────────────────────────────────────────
    t1, t2, t3, t4, t5 = (make_group(f"target-{i}") for i in range(1, 6))
    batch_a = main.create_group_batch(GroupBatchBase(name="Batch A", group_ids=[t1, t2, t3]))
    batch_b = main.create_group_batch(GroupBatchBase(name="Batch B", group_ids=[t3, t4, t5]))

    campaign = main.create_campaign(
        CampaignBase(
            name="Two batch campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[batch_a["id"], batch_b["id"]],
            batch_size=2,
        )
    )
    cid = campaign["id"]
    check(campaign["group_id"] is None, "batch campaign must store group_id = NULL")
    check(campaign["batch_ids"] == [batch_a["id"], batch_b["id"]], "create did not return batch_ids")

    rows = main.list_campaigns()
    listed_campaign = next(c for c in rows if c["id"] == cid)
    check(
        listed_campaign["batch_ids"] == [batch_a["id"], batch_b["id"]],
        "GET /campaigns did not attach batch_ids",
    )

    campaign_row = get_campaign(cid)
    pool = _batch_scope_groups(campaign_row)
    check(len(pool) == 5, f"duplicate groups across batches not counted once: {len(pool)}")
    check([g["id"] for g in pool].count(t3) == 1, "duplicate group appears more than once")

    picks = []
    for _ in range(3):
        picks.append([g["id"] for g in pick_group_batch(campaign_row)])
    check([len(p) for p in picks] == [2, 2, 1], f"unexpected batch sizes {[len(p) for p in picks]}")
    check(sum(picks, []) == [t1, t2, t3, t4, t5], f"batches did not cover the pool in order: {picks}")
    check(len(sum(picks, [])) == len(set(sum(picks, []))), "a group repeated before the cycle ended")
    check(_meta_get(f"campaign:{cid}:group_cursor") == 0, "cursor did not reset after final batch")
    next_pick = [g["id"] for g in pick_group_batch(campaign_row)]
    check(next_pick == [t1, t2], f"new cycle did not restart: {next_pick}")

    # Inactive groups are excluded at run time.
    db_logic.execute("UPDATE groups SET is_active = 0 WHERE id = ?", (t2,))
    inactive_pick = [g["id"] for g in pick_group_batch(campaign_row)]
    check(t2 not in inactive_pick, "inactive group was targeted")
    db_logic.execute("UPDATE groups SET is_active = 1 WHERE id = ?", (t2,))

    # Editing a batch changes the campaign's next eligible pool (live link).
    t6 = make_group("target-6")
    main.update_group_batch(
        batch_b["id"],
        GroupBatchBase(name="Batch B", group_ids=[t3, t4, t6]),
    )
    live_ids = {g["id"] for g in _batch_scope_groups(campaign_row)}
    check(t6 in live_ids and t5 not in live_ids, f"live membership not reflected: {live_ids}")

    # Changing the campaign's batch selection resets the group cursor.
    cursor_key = f"campaign:{cid}:group_cursor"
    _meta_set(cursor_key, t1)
    check(_meta_get(cursor_key) == t1, "cursor was not set for reset check")
    main.update_campaign(
        cid,
        CampaignBase(
            name="Two batch campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[batch_a["id"]],
            batch_size=2,
        ),
    )
    check(_meta_get(f"campaign:{cid}:group_cursor") == 0, "scope/batch update did not reset the cursor")

    # A batch campaign without batches is rejected.
    expect_http(
        400,
        lambda: main.create_campaign(
            CampaignBase(
                name="Missing batches",
                campaign_type="product_group",
                target_scope="batch",
                batch_ids=[],
                batch_size=2,
            )
        ),
        "batch campaign without batch_ids",
    )

    # ── paced cycle: full coverage, no early repeat, even after daily caps ─
    p1, p2, p3, p4, p5 = (make_group(f"pace-{i}") for i in range(1, 6))
    pace_a = main.create_group_batch(GroupBatchBase(name="Pace A", group_ids=[p1, p2, p3]))
    pace_b = main.create_group_batch(GroupBatchBase(name="Pace B", group_ids=[p3, p4, p5]))
    paced = main.create_campaign(
        CampaignBase(
            name="Paced batch campaign",
            campaign_type="product_group",
            target_scope="batch",
            batch_ids=[pace_a["id"], pace_b["id"]],
            batch_size=2,
        )
    )
    paced_cid = paced["id"]
    paced_row = get_campaign(paced_cid)
    seen: list[int] = []
    for _ in range(10):
        picked = pick_group_batch(paced_row)
        if not picked:
            break
        ids = [g["id"] for g in picked]
        seen.extend(ids)
        for group_id in ids:
            # n = 1, so posting caps the group for the rest of the day.
            mark_group_posted(group_id)
        if _cycle_complete(paced_cid, "group", paced_row):
            break
    check(seen == [p1, p2, p3, p4, p5], f"paced cycle repeated/skipped groups: {seen}")
    check(_meta_get(f"campaign:{paced_cid}:group_cursor") == 0, "paced cycle did not reset its cursor")
    db_logic.execute("UPDATE groups SET isPostedProductToday = 0")
    main.delete_campaign(paced_cid)

    # ── deletion rules ──────────────────────────────────────────────────
    expect_http(
        409,
        lambda: main.delete_group_batch(batch_a["id"]),
        "delete a batch used by a campaign",
    )
    main.delete_group_batch(created["id"])
    remaining = [b["id"] for b in main.list_group_batches()]
    check(created["id"] not in remaining, "unused batch was not deleted")

    # ── existing scopes stay unchanged ──────────────────────────────────
    single_group = make_group("single-target")
    single = main.create_campaign(
        CampaignBase(
            name="Single campaign",
            campaign_type="product_group",
            target_scope="single",
            group_id=single_group,
        )
    )
    single_row = get_campaign(single["id"])
    single_pick = pick_group_batch(single_row)
    check([g["id"] for g in single_pick] == [single_group], f"single scope changed: {single_pick}")
    check(main._campaign_batch_ids(single["id"]) == [], "single scope stored batch rows")

    all_campaign = main.create_campaign(
        CampaignBase(
            name="All campaign",
            campaign_type="product_group",
            target_scope="all",
            batch_size=2,
        )
    )
    all_row = get_campaign(all_campaign["id"])
    all_pick_1 = [g["id"] for g in pick_group_batch(all_row)]
    all_pick_2 = [g["id"] for g in pick_group_batch(all_row)]
    check(len(all_pick_1) == 2 and len(all_pick_2) == 2, "all scope batching changed")
    check(not set(all_pick_1) & set(all_pick_2), "all scope repeated groups early")
    check(main._campaign_batch_ids(all_campaign["id"]) == [], "all scope stored batch rows")
    check(all_row["target_scope"] == "all", "all scope was not preserved")

    client = main.create_client(ClientBase(name="Client", number="12345"))
    client_campaign = main.create_campaign(
        CampaignBase(
            name="Client campaign",
            campaign_type="product_client",
            target_scope="single",
            client_id=client["id"],
            client_ids=[client["id"]],
        )
    )
    check(main._campaign_batch_ids(client_campaign["id"]) == [], "product_client stored batch rows")

    link_campaign = main.create_campaign(
        CampaignBase(
            name="Link campaign",
            campaign_type="myGroupLink",
            target_scope="batch",
            group_id=single_group,
            batch_ids=[batch_b["id"]],
        )
    )
    check(link_campaign["target_scope"] == "all", "myGroupLink scope was not forced to all")
    check(main._campaign_batch_ids(link_campaign["id"]) == [], "myGroupLink stored batch rows")

    # ── campaign delete removes batch links ─────────────────────────────
    main.delete_campaign(cid)
    links = db_logic.query(
        "SELECT * FROM campaign_group_batches WHERE campaign_id = ?", (cid,)
    )
    check(not links, "campaign delete left campaign_group_batches rows")

    print("All group batch tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
