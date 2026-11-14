"""Single-row WhatsApp connection state plus live-run event mirroring.

``login_manager`` calls :func:`update_connection_state` at each meaningful
transition. The function deduplicates repeated polls and, when a run is active,
mirrors the state into ``campaign_run_events`` (and therefore the Live page).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from db_logic import get_conn

PAUSED_BY_CONNECTION = ("launching", "loading", "disconnected", "waiting_login", "waiting_qr", "reconnecting")


def get_connection_state() -> Dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {
            "state": "unknown",
            "message": None,
            "attempt": 0,
            "max_attempts": None,
            "qr_visible": False,
            "next_retry_at": None,
            "updated_at": None,
        }
    data = dict(row)
    data["qr_visible"] = bool(data.get("qr_visible"))
    return data


def update_connection_state(
    state: str,
    message: Optional[str] = None,
    *,
    attempt: int = 0,
    max_attempts: Optional[int] = None,
    qr_visible: bool = False,
    next_retry_at: Optional[str] = None,
) -> None:
    """Persist a connection transition, skipping no-op repeats."""
    state = state or "unknown"
    conn = get_conn()
    previous = conn.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
    changed = True
    if previous:
        changed = (
            previous["state"] != state
            or (previous["message"] or "") != (message or "")
            or int(previous["attempt"] or 0) != int(attempt or 0)
            or bool(previous["qr_visible"]) != bool(qr_visible)
        )
    if not changed:
        conn.close()
        return

    conn.execute(
        "INSERT INTO bot_state (id, state, message, attempt, max_attempts, qr_visible, "
        "next_retry_at, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET state = excluded.state, message = excluded.message, "
        "attempt = excluded.attempt, max_attempts = excluded.max_attempts, "
        "qr_visible = excluded.qr_visible, next_retry_at = excluded.next_retry_at, "
        "updated_at = excluded.updated_at",
        (state, message, int(attempt or 0), max_attempts, 1 if qr_visible else 0, next_retry_at),
    )

    run = conn.execute(
        "SELECT id, campaign_id, status FROM campaign_runs "
        "WHERE status IN ('starting', 'running', 'paused', 'waiting_login', 'waiting_qr', 'reconnecting') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if run:
        run_id = int(run["id"])
        conn.execute(
            "INSERT INTO campaign_run_events "
            "(run_id, campaign_id, level, event_type, message) "
            "VALUES (?, ?, ?, 'connection_state', ?)",
            (
                run_id,
                int(run["campaign_id"]),
                "error" if state == "error" else ("warning" if state in PAUSED_BY_CONNECTION else "info"),
                f"WhatsApp connection: {state}" + (f" ({message})" if message else ""),
            ),
        )
        if state == "connected":
            if run["status"] in ("waiting_login", "waiting_qr", "reconnecting", "paused"):
                conn.execute(
                    "UPDATE campaign_runs SET status = 'running', last_update = datetime('now') "
                    "WHERE id = ?",
                    (run_id,),
                )
        elif state in ("waiting_login", "waiting_qr"):
            conn.execute(
                "UPDATE campaign_runs SET status = ?, last_update = datetime('now') WHERE id = ?",
                (state, run_id),
            )
        elif state in ("launching", "loading", "disconnected", "reconnecting"):
            conn.execute(
                "UPDATE campaign_runs SET status = 'reconnecting', last_update = datetime('now') "
                "WHERE id = ?",
                (run_id,),
            )
    conn.commit()
    conn.close()
