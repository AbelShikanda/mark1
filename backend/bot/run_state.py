"""Structured live-run state for the campaign runner.

The runner is synchronous and single-threaded per campaign, while the API reads
the same state from request threads. Everything here is therefore persisted in
SQLite (``campaign_runs``, ``campaign_run_targets``, ``campaign_run_events``),
with only the skip request kept as an in-process event.

No Playwright / WhatsApp objects are touched by this module.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from db_logic import get_conn, log

ACTIVE_STATUSES = (
    "starting",
    "running",
    "paused",
    "waiting_login",
    "waiting_qr",
    "reconnecting",
)

PROCESSED_STATUSES = ("sent", "failed", "skipped", "deferred")

# Events that are also written to the flat ``logs`` table so the Logs page
# stays useful without duplicating every fine-grained progress line.
_LOG_EVENTS = {
    "run_started",
    "run_finished",
    "batch_started",
    "target_sent",
    "target_failed",
    "target_skipped",
    "target_deferred",
    "group_silenced",
    "connection_state",
    "error",
}

_skip_lock = threading.Lock()
_skip_events: Dict[int, threading.Event] = {}


# ── small helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_dict(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def _dicts(rows) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def active_run_id() -> Optional[int]:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM campaign_runs WHERE status IN ({}) ORDER BY id DESC LIMIT 1".format(
            ",".join("?" for _ in ACTIVE_STATUSES)
        ),
        ACTIVE_STATUSES,
    ).fetchone()
    conn.close()
    return int(row["id"]) if row else None


# ── skip requests ────────────────────────────────────────────────────────


def _skip_event(campaign_id: int) -> threading.Event:
    with _skip_lock:
        return _skip_events.setdefault(int(campaign_id), threading.Event())


def request_skip(campaign_id: int) -> None:
    """Ask the runner to skip the current target as soon as it can."""
    _skip_event(campaign_id).set()
    conn = get_conn()
    conn.execute(
        "UPDATE campaign_runs SET skip_requested = 1, last_update = datetime('now') "
        "WHERE campaign_id = ? AND status IN ({})".format(
            ",".join("?" for _ in ACTIVE_STATUSES)
        ),
        (campaign_id,) + ACTIVE_STATUSES,
    )
    conn.commit()
    conn.close()


def skip_requested(campaign_id: int) -> bool:
    with _skip_lock:
        event = _skip_events.get(int(campaign_id))
        return bool(event and event.is_set())


def clear_skip(campaign_id: int) -> bool:
    """Clear a pending skip request and report whether one was pending."""
    with _skip_lock:
        event = _skip_events.get(int(campaign_id))
        was_set = bool(event and event.is_set())
        if event:
            event.clear()
    conn = get_conn()
    conn.execute(
        "UPDATE campaign_runs SET skip_requested = 0, last_update = datetime('now') "
        "WHERE campaign_id = ?",
        (campaign_id,),
    )
    conn.commit()
    conn.close()
    return was_set


# Backwards-friendly alias: the runner "consumes" a skip at a checkpoint.
def consume_skip(campaign_id: int) -> bool:
    return clear_skip(campaign_id)


# ── run lifecycle ────────────────────────────────────────────────────────


def start_run(campaign: Dict[str, Any], product: Optional[Dict[str, Any]] = None) -> int:
    clear_skip(campaign["id"])
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO campaign_runs "
        "(campaign_id, campaign_name, campaign_type, status, phase, product_id, "
        " product_name, started_at, last_update) "
        "VALUES (?, ?, ?, 'starting', 'resolving_targets', ?, ?, datetime('now'), datetime('now'))",
        (
            campaign["id"],
            campaign.get("name"),
            campaign.get("campaign_type"),
            (product or {}).get("id"),
            (product or {}).get("name"),
        ),
    )
    run_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    record_event(
        run_id,
        "info",
        "run_started",
        f"Run started for '{campaign.get('name') or campaign['id']}'",
        campaign_id=campaign["id"],
    )
    return run_id


def set_run_product(
    run_id: Optional[int],
    product: Optional[Dict[str, Any]] = None,
    *,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
) -> None:
    if not run_id:
        return
    if product:
        product_id = product.get("id")
        product_name = product.get("name")
    conn = get_conn()
    conn.execute(
        "UPDATE campaign_runs SET product_id = ?, product_name = ?, last_update = datetime('now') "
        "WHERE id = ?",
        (product_id, product_name, run_id),
    )
    conn.commit()
    conn.close()


def set_run_phase(
    run_id: Optional[int],
    *,
    status: Optional[str] = None,
    phase: Optional[str] = None,
    message: Optional[str] = None,
    cycle_complete: Optional[bool] = None,
    error: Optional[str] = None,
) -> None:
    if not run_id:
        return
    fields: List[str] = []
    params: List[Any] = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if phase is not None:
        fields.append("phase = ?")
        params.append(phase)
    if cycle_complete is not None:
        fields.append("cycle_complete = ?")
        params.append(1 if cycle_complete else 0)
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    fields.append("last_update = datetime('now')")
    params.append(run_id)
    conn = get_conn()
    conn.execute(f"UPDATE campaign_runs SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    if message:
        record_event(run_id, "info", "progress", message)


def finish_run(run_id: Optional[int], status: str, error: Optional[str] = None) -> None:
    if not run_id:
        return
    conn = get_conn()
    row = conn.execute("SELECT campaign_id FROM campaign_runs WHERE id = ?", (run_id,)).fetchone()
    conn.execute(
        "UPDATE campaign_runs SET status = ?, phase = 'finished', finished_at = datetime('now'), "
        "last_update = datetime('now'), current_target_id = NULL, current_target_name = NULL, "
        "error = COALESCE(?, error) WHERE id = ?",
        (status, error, run_id),
    )
    conn.commit()
    conn.close()
    if row:
        clear_skip(int(row["campaign_id"]))
    level = "error" if status == "failed" else "info"
    record_event(
        run_id,
        level,
        "run_finished",
        f"Run {status}" + (f": {error}" if error else ""),
        campaign_id=int(row["campaign_id"]) if row else None,
    )


def next_batch_no(run_id: Optional[int]) -> int:
    if not run_id:
        return 1
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(MAX(batch_no), 0) AS n FROM campaign_run_targets WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    conn.close()
    return int(row["n"] if row else 0) + 1


# ── targets ──────────────────────────────────────────────────────────────


def create_run_targets(
    run_id: Optional[int],
    campaign_id: int,
    targets: Iterable[Dict[str, Any]],
    *,
    target_type: str = "group",
    batch_no: Optional[int] = None,
    source_name: Optional[str] = None,
) -> int:
    """Create pending rows for one selected batch chunk. Returns rows inserted."""
    if not run_id:
        return 0
    batch_no = batch_no or next_batch_no(run_id)
    inserted = 0
    conn = get_conn()
    for index, target in enumerate(targets):
        cur = conn.execute(
            "INSERT OR IGNORE INTO campaign_run_targets "
            "(run_id, campaign_id, batch_no, queue_index, target_type, target_id, "
            " target_name, source_name, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                run_id,
                campaign_id,
                batch_no,
                index,
                target_type,
                target.get("id"),
                target.get("name"),
                source_name,
            ),
        )
        inserted += 1 if cur.rowcount else 0
    conn.commit()
    conn.close()
    if inserted:
        recompute_counts(run_id)
        record_event(
            run_id,
            "info",
            "batch_started",
            f"Batch {batch_no}: {inserted} {target_type}(s) queued",
            campaign_id=campaign_id,
        )
    return inserted


def set_current_target(
    run_id: Optional[int],
    target_type: str,
    target_id: int,
    target_name: Optional[str] = None,
    *,
    phase: Optional[str] = None,
) -> None:
    if not run_id:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE campaign_runs SET target_type = ?, current_target_id = ?, "
        "current_target_name = ?, phase = COALESCE(?, phase), last_update = datetime('now') "
        "WHERE id = ?",
        (target_type, target_id, target_name, phase, run_id),
    )
    conn.execute(
        "UPDATE campaign_run_targets SET status = 'current', "
        "started_at = COALESCE(started_at, datetime('now')), message = NULL "
        "WHERE run_id = ? AND target_type = ? AND target_id = ?",
        (run_id, target_type, target_id),
    )
    conn.commit()
    conn.close()


def release_current_target(
    run_id: Optional[int],
    target_type: str,
    target_id: int,
    message: Optional[str] = None,
) -> None:
    """Put a target back to pending (e.g. connection lost before an attempt).

    This deliberately does not increment the attempt/miss counters: losing the
    WhatsApp connection must not blame the group.
    """
    if not run_id:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE campaign_run_targets SET status = 'pending', message = ?, "
        "started_at = NULL, finished_at = NULL "
        "WHERE run_id = ? AND target_type = ? AND target_id = ? "
        "AND status = 'current'",
        (message, run_id, target_type, target_id),
    )
    conn.execute(
        "UPDATE campaign_runs SET current_target_id = NULL, current_target_name = NULL, "
        "last_update = datetime('now') WHERE id = ?",
        (run_id,),
    )
    conn.commit()
    conn.close()
    recompute_counts(run_id)


def recompute_counts(run_id: int) -> Dict[str, int]:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(status = 'sent'), 0) AS sent, "
        "COALESCE(SUM(status = 'failed'), 0) AS failed, "
        "COALESCE(SUM(status = 'skipped'), 0) AS skipped, "
        "COALESCE(SUM(status = 'deferred'), 0) AS deferred, "
        "COALESCE(SUM(status IN ('sent', 'failed', 'skipped', 'deferred')), 0) AS processed, "
        "COALESCE(SUM(status IN ('pending', 'current')), 0) AS remaining "
        "FROM campaign_run_targets WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    counts = {key: int(row[key]) for key in row.keys()} if row else {}
    conn.execute(
        "UPDATE campaign_runs SET total_targets = ?, processed = ?, sent = ?, failed = ?, "
        "skipped = ?, remaining = ?, last_update = datetime('now') WHERE id = ?",
        (
            counts.get("total", 0),
            counts.get("processed", 0),
            counts.get("sent", 0),
            counts.get("failed", 0),
            counts.get("skipped", 0),
            counts.get("remaining", 0),
            run_id,
        ),
    )
    conn.commit()
    conn.close()
    return counts


_EVENT_TYPES = {
    "sent": ("info", "target_sent"),
    "failed": ("warning", "target_failed"),
    "skipped": ("info", "target_skipped"),
    "deferred": ("info", "target_deferred"),
}


def record_target_result(
    run_id: Optional[int],
    target_type: str,
    target_id: int,
    status: str,
    message: Optional[str] = None,
    *,
    target_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
) -> None:
    if not run_id:
        return
    level, event_type = _EVENT_TYPES.get(status, ("info", "progress"))
    conn = get_conn()
    cur = conn.execute(
        "UPDATE campaign_run_targets SET status = ?, message = ?, "
        "attempts = attempts + 1, finished_at = datetime('now'), "
        "target_name = COALESCE(target_name, ?) "
        "WHERE run_id = ? AND target_type = ? AND target_id = ?",
        (status, message, target_name, run_id, target_type, target_id),
    )
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO campaign_run_targets "
            "(run_id, campaign_id, target_type, target_id, target_name, status, "
            " attempts, message, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'))",
            (
                run_id,
                campaign_id or 0,
                target_type,
                target_id,
                target_name,
                status,
                message,
            ),
        )
    conn.commit()
    conn.close()
    recompute_counts(run_id)
    record_event(
        run_id,
        level,
        event_type,
        message or f"{target_type} {target_name or target_id} {status}",
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        campaign_id=campaign_id,
    )


# ── events ───────────────────────────────────────────────────────────────


def record_event(
    run_id: Optional[int],
    level: str,
    event_type: str,
    message: str,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    target_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    write_log: Optional[bool] = None,
) -> None:
    if not message:
        return
    conn = get_conn()
    if campaign_id is None and run_id:
        row = conn.execute(
            "SELECT campaign_id FROM campaign_runs WHERE id = ?", (run_id,)
        ).fetchone()
        campaign_id = int(row["campaign_id"]) if row else None
    conn.execute(
        "INSERT INTO campaign_run_events "
        "(run_id, campaign_id, level, event_type, target_type, target_id, "
        " target_name, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            campaign_id,
            level,
            event_type,
            target_type,
            target_id,
            target_name,
            message,
        ),
    )
    conn.commit()
    conn.close()
    if write_log is None:
        write_log = event_type in _LOG_EVENTS
    if write_log:
        log(level, message, "campaign_runner")


# ── read helpers used by the live API ────────────────────────────────────


def get_run(run_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaign_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return _row_dict(row)


def get_active_run(campaign_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM campaign_runs WHERE status IN ({})".format(
        ",".join("?" for _ in ACTIVE_STATUSES)
    )
    params: List[Any] = list(ACTIVE_STATUSES)
    if campaign_id is not None:
        sql += " AND campaign_id = ?"
        params.append(campaign_id)
    sql += " ORDER BY id DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return _row_dict(row)


def list_runs(limit: int = 20, campaign_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM campaign_runs"
    params: List[Any] = []
    if campaign_id is not None:
        sql += " WHERE campaign_id = ?"
        params.append(campaign_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return _dicts(rows)


def list_run_targets(run_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM campaign_run_targets WHERE run_id = ?"
    params: List[Any] = [run_id]
    if status:
        statuses = [part.strip() for part in str(status).split(",") if part.strip()]
        if statuses:
            sql += " AND status IN ({})".format(",".join("?" for _ in statuses))
            params.extend(statuses)
    sql += " ORDER BY batch_no, queue_index, id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return _dicts(rows)


def list_run_events(
    run_id: int, after_id: int = 0, limit: int = 200
) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM campaign_run_events WHERE run_id = ? AND id > ? "
        "ORDER BY id ASC LIMIT ?",
        (run_id, max(0, int(after_id)), max(1, min(int(limit), 1000))),
    ).fetchall()
    conn.close()
    return _dicts(rows)
