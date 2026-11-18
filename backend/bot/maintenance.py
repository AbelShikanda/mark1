"""Maintenance helpers for logs, run history and debug artifacts.

Everything here is deliberately conservative: the destructive helpers in this
module only ever touch operational history (``logs``, finished
``campaign_runs``/targets/events and ``data/debug``). Products, groups,
clients, campaigns, schedules, analytics, campaign posts, settings and the
saved WhatsApp session are never removed by "clear all safe" or by the
automatic retention cleanup.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config import DATA_DIR, DB_PATH, SESSION_DIR
from db_logic import get_conn, log

# Kept local so this module can be imported without pulling in the runner.
ACTIVE_RUN_STATUSES = (
    "starting",
    "running",
    "paused",
    "waiting_login",
    "waiting_qr",
    "reconnecting",
)

LAST_RETENTION_KEY = "last_retention_run"


# ── small helpers ───────────────────────────────────────────────────────


def _dir_files(directory: Path) -> List[Path]:
    try:
        if not directory.exists():
            return []
        return [path for path in directory.rglob("*") if path.is_file()]
    except Exception:
        return []


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0


def _dir_bytes(directory: Path) -> int:
    return sum(_file_bytes(path) for path in _dir_files(directory))


def _db_bytes() -> int:
    total = _file_bytes(Path(DB_PATH))
    for suffix in ("-wal", "-shm"):
        total += _file_bytes(Path(str(DB_PATH) + suffix))
    return total


def _placeholders(values: Iterable[str]) -> str:
    return ",".join("?" for _ in values)


def _cutoff(days: int) -> str:
    days = max(1, int(days))
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _debug_dir() -> Path:
    return Path(DATA_DIR) / "debug"


def _audit(message: str) -> None:
    try:
        log("info", f"[maintenance] {message}", "maintenance")
    except Exception:
        pass


def vacuum_db() -> None:
    """Compact the database after an explicit clear (best effort)."""
    try:
        conn = get_conn()
        conn.execute("VACUUM")
        conn.close()
    except Exception:
        pass


def get_last_retention_run() -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = ?", (LAST_RETENTION_KEY,)
    ).fetchone()
    conn.close()
    return row["value"] if row and row["value"] else None


def _set_last_retention_run(value: str | None = None) -> str:
    stamp = value or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (LAST_RETENTION_KEY, stamp),
    )
    conn.commit()
    conn.close()
    return stamp


# ── read-only stats ─────────────────────────────────────────────────────


def stats() -> Dict[str, Any]:
    """Counts and byte sizes shown on the Settings > Data & Maintenance card."""
    conn = get_conn()
    counts = {
        "logs": int(conn.execute("SELECT COUNT(*) AS c FROM logs").fetchone()["c"]),
        "campaign_runs": int(conn.execute("SELECT COUNT(*) AS c FROM campaign_runs").fetchone()["c"]),
        "run_targets": int(conn.execute("SELECT COUNT(*) AS c FROM campaign_run_targets").fetchone()["c"]),
        "run_events": int(conn.execute("SELECT COUNT(*) AS c FROM campaign_run_events").fetchone()["c"]),
        "active_runs": int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM campaign_runs WHERE status IN ({})".format(
                    _placeholders(ACTIVE_RUN_STATUSES)
                ),
                ACTIVE_RUN_STATUSES,
            ).fetchone()["c"]
        ),
        "finished_runs": int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM campaign_runs WHERE status NOT IN ({})".format(
                    _placeholders(ACTIVE_RUN_STATUSES)
                ),
                ACTIVE_RUN_STATUSES,
            ).fetchone()["c"]
        ),
    }
    conn.close()

    debug_dir = _debug_dir()
    debug_files = _dir_files(debug_dir)
    return {
        "logs": counts["logs"],
        "campaign_runs": counts["campaign_runs"],
        "active_runs": counts["active_runs"],
        "finished_runs": counts["finished_runs"],
        "run_targets": counts["run_targets"],
        "run_events": counts["run_events"],
        "debug_files": len(debug_files),
        "debug_bytes": sum(_file_bytes(path) for path in debug_files),
        "database_bytes": _db_bytes(),
        "session_bytes": _dir_bytes(Path(SESSION_DIR)),
        "database_path": str(DB_PATH),
        "session_path": str(SESSION_DIR),
        "last_retention_run": get_last_retention_run(),
    }


# ── explicit clears ─────────────────────────────────────────────────────


def clear_logs(*, audit: bool = True, vacuum: bool = True) -> Dict[str, int]:
    conn = get_conn()
    deleted = int(conn.execute("DELETE FROM logs").rowcount or 0)
    conn.commit()
    conn.close()
    if audit:
        _audit(f"cleared {deleted} log entries")
    if vacuum:
        vacuum_db()
    return {"logs": deleted}


def clear_finished_runs(*, audit: bool = True, vacuum: bool = True) -> Dict[str, int]:
    """Delete finished runs and their targets/events; active runs stay put."""
    conn = get_conn()
    params = list(ACTIVE_RUN_STATUSES)
    where = "status NOT IN ({})".format(_placeholders(ACTIVE_RUN_STATUSES))
    run_ids = [
        int(row["id"])
        for row in conn.execute(f"SELECT id FROM campaign_runs WHERE {where}", params).fetchall()
    ]
    targets = events = runs = 0
    if run_ids:
        id_where = _placeholders([str(i) for i in run_ids])
        targets = int(
            conn.execute(
                f"DELETE FROM campaign_run_targets WHERE run_id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
        events = int(
            conn.execute(
                f"DELETE FROM campaign_run_events WHERE run_id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
        runs = int(
            conn.execute(
                f"DELETE FROM campaign_runs WHERE id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
    conn.commit()
    conn.close()
    if audit:
        _audit(f"cleared {runs} finished run(s), {targets} target row(s), {events} event(s)")
    if vacuum:
        vacuum_db()
    return {"runs": runs, "targets": targets, "events": events}


def clear_debug_files(*, audit: bool = True, vacuum: bool = True) -> Dict[str, int]:
    deleted = 0
    freed = 0
    for path in _dir_files(_debug_dir()):
        size = _file_bytes(path)
        try:
            path.unlink()
        except Exception:
            continue
        deleted += 1
        freed += size
    if audit:
        _audit(f"cleared {deleted} debug file(s) ({freed} bytes)")
    if vacuum:
        vacuum_db()
    return {"files": deleted, "bytes": freed}


def clear_all_safe(*, vacuum: bool = True) -> Dict[str, Any]:
    """Clear operational history only; never configuration or analytics."""
    logs = clear_logs(audit=False, vacuum=False)
    runs = clear_finished_runs(audit=False, vacuum=False)
    debug = clear_debug_files(audit=False, vacuum=False)
    _audit(
        "cleared safe operational data: "
        f"{logs['logs']} log entry(s), {runs['runs']} finished run(s), "
        f"{debug['files']} debug file(s)"
    )
    if vacuum:
        vacuum_db()
    return {"logs": logs["logs"], **runs, "debug_files": debug["files"], "debug_bytes": debug["bytes"]}


# ── automatic retention ─────────────────────────────────────────────────


def purge_old_messages() -> int:
    """Delete raw captured group messages past the user-set retention.

    Spam-flagged or human-reviewed rows are kept because they are training
    material/value for the review queue; reports only ever hold aggregates, so
    deleting raw rows never corrupts a saved report.
    """
    from bot import settings as app_settings  # local import to avoid a cycle

    days = max(1, app_settings.get_int("message_retention_days", 30))
    keep_flagged = app_settings.get_bool("keep_flagged_messages", True)
    cutoff = _cutoff(days)
    conn = get_conn()
    if keep_flagged:
        deleted = int(
            conn.execute(
                "DELETE FROM group_messages WHERE captured_at < ? AND spam_flag = 0 AND reviewed = 0",
                (cutoff,),
            ).rowcount
            or 0
        )
    else:
        deleted = int(
            conn.execute("DELETE FROM group_messages WHERE captured_at < ?", (cutoff,)).rowcount or 0
        )
    conn.commit()
    conn.close()
    return deleted


def retention_cleanup(days: int, *, vacuum: bool = False) -> Dict[str, Any]:
    """Delete logs, finished runs and debug files older than ``days``."""
    days = max(1, min(3650, int(days or 30)))
    cutoff = _cutoff(days)
    now = time.time()
    age_seconds = days * 86400

    conn = get_conn()
    logs_deleted = int(
        conn.execute("DELETE FROM logs WHERE created_at < ?", (cutoff,)).rowcount or 0
    )

    run_where = (
        "status NOT IN ({}) AND "
        "COALESCE(finished_at, started_at, last_update, '') != '' AND "
        "COALESCE(finished_at, started_at, last_update) < ?"
    ).format(_placeholders(ACTIVE_RUN_STATUSES))
    run_params = list(ACTIVE_RUN_STATUSES) + [cutoff]
    run_ids = [
        int(row["id"])
        for row in conn.execute(
            f"SELECT id FROM campaign_runs WHERE {run_where}", run_params
        ).fetchall()
    ]
    runs_deleted = targets_deleted = events_deleted = 0
    if run_ids:
        id_where = _placeholders([str(i) for i in run_ids])
        targets_deleted = int(
            conn.execute(
                f"DELETE FROM campaign_run_targets WHERE run_id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
        events_deleted = int(
            conn.execute(
                f"DELETE FROM campaign_run_events WHERE run_id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
        runs_deleted = int(
            conn.execute(
                f"DELETE FROM campaign_runs WHERE id IN ({id_where})", run_ids
            ).rowcount
            or 0
        )
    conn.commit()
    conn.close()
    message_deleted = purge_old_messages()
    if message_deleted:
        log("info", f"retention purged {message_deleted} raw captured message(s)", "maintenance")

    debug_deleted = 0
    debug_bytes = 0
    for path in _dir_files(_debug_dir()):
        try:
            age = now - path.stat().st_mtime
        except Exception:
            continue
        if age <= age_seconds:
            continue
        size = _file_bytes(path)
        try:
            path.unlink()
        except Exception:
            continue
        debug_deleted += 1
        debug_bytes += size

    stamp = _set_last_retention_run()
    summary = {
        "days": days,
        "cutoff": cutoff,
        "logs": logs_deleted,
        "runs": runs_deleted,
        "targets": targets_deleted,
        "events": events_deleted,
        "debug_files": debug_deleted,
        "debug_bytes": debug_bytes,
        "ran_at": stamp,
    }
    _audit(
        f"retention cleanup ({days}d, cutoff {cutoff}): "
        f"{logs_deleted} log(s), {runs_deleted} run(s), "
        f"{debug_deleted} debug file(s) removed"
    )
    if vacuum:
        vacuum_db()
    return summary


def maybe_retention_cleanup(days: int, *, min_interval_hours: int = 24) -> Dict[str, Any] | None:
    """Run retention at most once per interval; returns None when skipped."""
    last = get_last_retention_run()
    if last:
        try:
            previous = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            if datetime.now() - previous < timedelta(hours=max(1, min_interval_hours)):
                return None
        except ValueError:
            pass
    return retention_cleanup(days)


def remove_empty_dirs(directory: Path) -> None:
    """Small utility used by tests/ops; never touches files outside ``directory``."""
    try:
        for child in sorted(directory.rglob("*"), reverse=True):
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
    except Exception:
        pass
