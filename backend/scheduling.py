"""Campaign time model.

The campaign owns its run time. A schedule row is *generated* from a campaign
so the calendar view always mirrors what the campaign will actually do.

Rules implemented here:
- one-shot campaigns run once at ``scheduled_time``;
- ``repeatPost`` campaigns re-run daily / weekly / monthly at ``repeat_time``
  (and ``repeat_day`` for weekly/monthly);
- every generated slot is moved forward to the next free slot when it would
  overlap an existing campaign, so the calendar never has double bookings.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from db_logic import get_conn

FMT = "%Y-%m-%d %H:%M"
FREQUENCIES = {"daily", "weekly", "monthly"}


def now_minute() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in (FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def fmt_dt(value: datetime) -> str:
    return value.strftime(FMT)


def _parse_time(value: Optional[str]) -> Tuple[int, int]:
    if value:
        try:
            hour, minute = value.strip().split(":")[:2]
            return int(hour), int(minute)
        except (ValueError, AttributeError):
            pass
    return 9, 0


def _base_campaign_time(campaign: Dict[str, Any]) -> Optional[datetime]:
    start = parse_dt(campaign.get("scheduled_time"))
    if start is not None:
        return start
    if campaign.get("repeatPost"):
        return now_minute()
    return None


def compute_next_run(campaign: Dict[str, Any], after: Optional[datetime] = None) -> Optional[str]:
    """Return the next time this campaign should run (``None`` = one-shot done)."""
    base = _base_campaign_time(campaign)
    if base is None:
        return None

    if not campaign.get("repeatPost"):
        return fmt_dt(base)

    frequency = (campaign.get("frequency") or "daily").lower()
    if frequency not in FREQUENCIES:
        frequency = "daily"
    hour, minute = _parse_time(campaign.get("repeat_time") or fmt_dt(base)[11:])
    reference = after or now_minute()

    # The first run may be in the future; otherwise walk forward from the
    # reference time until we land on the next matching occurrence.
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > reference:
        return fmt_dt(candidate)

    day = campaign.get("repeat_day")
    try:
        day = int(day) if day is not None else None
    except (TypeError, ValueError):
        day = None

    if frequency == "daily":
        candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= reference:
            candidate += timedelta(days=1)
        return fmt_dt(candidate)

    if frequency == "weekly":
        target_weekday = day if day is not None else 0  # 0 = Monday
        target_weekday = max(0, min(6, target_weekday))
        candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = (target_weekday - candidate.weekday()) % 7
        candidate += timedelta(days=delta)
        if candidate <= reference:
            candidate += timedelta(days=7)
        return fmt_dt(candidate)

    # monthly
    target_day = day if day is not None else 1
    target_day = max(1, min(31, target_day))
    year, month = reference.year, reference.month
    while True:
        last_day = calendar.monthrange(year, month)[1]
        candidate = datetime(year, month, min(target_day, last_day), hour, minute)
        if candidate > reference:
            return fmt_dt(candidate)
        month += 1
        if month > 12:
            month = 1
            year += 1


def find_next_free_slot(
    wanted_start: datetime,
    duration_minutes: int = 60,
    exclude_campaign_id: Optional[int] = None,
) -> datetime:
    """First slot at/after ``wanted_start`` that does not overlap a campaign slot."""
    duration = max(5, int(duration_minutes or 60))
    candidate = max(wanted_start, now_minute())
    conn = get_conn()
    params: list[Any] = []
    sql = "SELECT campaign_id, start_time, end_time FROM schedules WHERE status = 'active'"
    if exclude_campaign_id is not None:
        sql += " AND campaign_id != ?"
        params.append(exclude_campaign_id)
    rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    conn.close()

    slots = sorted(
        (parse_dt(r["start_time"]), parse_dt(r["end_time"]))
        for r in rows
        if parse_dt(r["start_time"]) and parse_dt(r["end_time"])
    )
    for _ in range(500):
        candidate_end = candidate + timedelta(minutes=duration)
        conflict = None
        for start, end in slots:
            if start < candidate_end and end > candidate:
                conflict = end
                break
        if conflict is None:
            return candidate
        candidate = conflict
    return candidate


def next_free_slot_for_campaign(campaign: Dict[str, Any], from_time: Optional[datetime] = None) -> str:
    wanted = parse_dt(campaign.get("next_run_at")) or parse_dt(campaign.get("scheduled_time")) or now_minute()
    if from_time is not None:
        wanted = max(wanted, from_time)
    return fmt_dt(
        find_next_free_slot(
            wanted,
            int(campaign.get("duration_minutes") or 60),
            campaign.get("id"),
        )
    )


def _write_schedule(cid: int, next_run: Optional[str], duration_minutes: int = 60) -> Optional[str]:
    """Persist a campaign's next run and its generated schedule row."""
    conn = get_conn()
    if next_run:
        start = parse_dt(next_run)
        if start is None:
            conn.close()
            return None
        end = fmt_dt(start + timedelta(minutes=max(5, int(duration_minutes or 60))))
        conn.execute("UPDATE campaigns SET next_run_at = ? WHERE id = ?", (fmt_dt(start), cid))
        conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
        conn.execute(
            "INSERT INTO schedules (campaign_id, start_time, end_time, status) VALUES (?, ?, ?, 'active')",
            (cid, fmt_dt(start), end),
        )
    else:
        conn.execute("UPDATE campaigns SET next_run_at = NULL WHERE id = ?", (cid,))
        conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
    conn.commit()
    conn.close()
    refresh_pending_products()
    return next_run


def sync_campaign_schedule(cid: int) -> Optional[str]:
    """Rebuild the campaign's generated schedule row and return its next run."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        return None
    campaign = dict(row)

    next_run = compute_next_run(campaign)
    if next_run:
        free = find_next_free_slot(
            parse_dt(next_run),
            int(campaign.get("duration_minutes") or 60),
            cid,
        )
        next_run = fmt_dt(free)
    return _write_schedule(cid, next_run, int(campaign.get("duration_minutes") or 60))


def advance_after_run(cid: int) -> Optional[str]:
    """Move a repeat campaign to its next occurrence; finish a one-shot campaign."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        return None
    campaign = dict(row)
    if not campaign.get("repeatPost"):
        conn = get_conn()
        conn.execute("UPDATE campaigns SET next_run_at = NULL WHERE id = ?", (cid,))
        conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()
        return None

    anchor = max(now_minute(), parse_dt(campaign.get("next_run_at")) or now_minute())
    upcoming = compute_next_run(campaign, after=anchor)
    if upcoming:
        free = find_next_free_slot(
            parse_dt(upcoming),
            int(campaign.get("duration_minutes") or 60),
            cid,
        )
        upcoming = fmt_dt(free)
    _write_schedule(cid, upcoming, int(campaign.get("duration_minutes") or 60))
    return upcoming


def defer_campaign(cid: int) -> Optional[str]:
    """Busy handling: push a campaign to the next free slot instead of retrying."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        return None
    campaign = dict(row)
    current = parse_dt(campaign.get("next_run_at")) or now_minute()
    free = find_next_free_slot(
        current + timedelta(minutes=1),
        int(campaign.get("duration_minutes") or 60),
        cid,
    )
    conn = get_conn()
    conn.execute(
        "UPDATE campaigns SET scheduled_time = ?, status = 'isScheduledFor' WHERE id = ?",
        (fmt_dt(free), cid),
    )
    conn.commit()
    conn.close()
    _write_schedule(cid, fmt_dt(free), int(campaign.get("duration_minutes") or 60))
    return fmt_dt(free)


# ── isPending helpers ───────────────────────────────────────────────────


def _product_has_scheduled_campaign(product_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM campaigns "
        "WHERE product_id = ? AND auto_product = 0 AND next_run_at IS NOT NULL "
        "AND status IN ('isScheduledFor', 'isBusy', 'isRunning')",
        (product_id,),
    ).fetchone()
    conn.close()
    return bool(row and row["c"])


def set_campaign_pending_product(cid: int) -> None:
    """A fixed product becomes isPending as soon as its campaign is scheduled."""
    conn = get_conn()
    row = conn.execute(
        "SELECT product_id, auto_product, next_run_at, status FROM campaigns WHERE id = ?",
        (cid,),
    ).fetchone()
    conn.close()
    if not row or row["auto_product"] or not row["product_id"]:
        return
    if not row["next_run_at"] or row["status"] not in ("isScheduledFor", "isBusy", "isRunning"):
        return
    conn = get_conn()
    conn.execute(
        "UPDATE products SET status = 'isPending', updated_at = datetime('now') "
        "WHERE id = ? AND status = 'isNotPosted'",
        (row["product_id"],),
    )
    conn.commit()
    conn.close()


def clear_pending_if_unused(product_id: Optional[int]) -> None:
    if not product_id:
        return
    if _product_has_scheduled_campaign(int(product_id)):
        return
    conn = get_conn()
    conn.execute(
        "UPDATE products SET status = 'isNotPosted', updated_at = datetime('now') "
        "WHERE id = ? AND status = 'isPending'",
        (product_id,),
    )
    conn.commit()
    conn.close()


def refresh_pending_products() -> None:
    """Keep isPending in sync with scheduled campaigns; drop stale pending flags."""
    conn = get_conn()
    pending = conn.execute("SELECT id FROM products WHERE status = 'isPending'").fetchall()
    conn.close()
    for row in pending:
        clear_pending_if_unused(row["id"])
