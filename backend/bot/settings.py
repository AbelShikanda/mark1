"""Runtime automation settings.

Values are stored in ``app_meta`` and override the env/config defaults, so the
dashboard can tune the bot without restarting it. Every entry carries the
metadata needed to render the settings page, which keeps adding future options
(including the pre-set parameters from the ``adopt`` modules) a data change
rather than a UI rewrite.
"""

from __future__ import annotations

from typing import Any, Dict, List

import config
from db_logic import get_conn, log

# Each setting: key, label, description, type, default, min/max, category, unit.
SETTINGS: List[Dict[str, Any]] = [
    {
        "key": "qr_after_logins",
        "label": "Ask for QR after N runs",
        "description": "Clear the saved WhatsApp profile and show a fresh QR code after this many campaign runs. With the saved session, most runs connect in seconds once the initial sync is done. Set 1 to force a QR before every run (slowest, re-downloads the whole chat list).",
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 100,
        "category": "Session",
        "unit": "runs",
    },
    {
        "key": "login_timeout_seconds",
        "label": "WhatsApp login timeout",
        "description": "How long to wait for WhatsApp Web to reach a logged-in state before giving up this run.",
        "type": "int",
        "default": config.LOGIN_TIMEOUT,
        "min": 30,
        "max": 1800,
        "category": "Session",
        "unit": "seconds",
    },
    {
        "key": "connection_wait_seconds",
        "label": "WhatsApp reconnect budget",
        "description": "How long to keep trying to recover WhatsApp (reload / re-login) before the run gives up.",
        "type": "int",
        "default": config.CONNECTION_WAIT_TIMEOUT,
        "min": 30,
        "max": 3600,
        "category": "Session",
        "unit": "seconds",
    },
    {
        "key": "session_sync_wait",
        "label": "Post-link chat sync timeout",
        "description": "After a fresh QR scan WhatsApp re-downloads the whole chat list. This is how long the bot waits for the sync to finish before it refuses to post instead of posting blind. Anti-detection: the bot does not post while 'Loading your chats' is on screen.",
        "type": "int",
        "default": 600,
        "min": 30,
        "max": 3600,
        "category": "Session",
        "unit": "seconds",
    },
    {
        "key": "headless",
        "label": "Run browser headless",
        "description": "Hide the Chrome window. QR codes are shown in the dashboard by default; a visible browser is available as a fallback.",
        "type": "bool",
        "default": False,
        "category": "Session",
    },
    {
        "key": "live_poll_ms",
        "label": "Live page poll interval",
        "description": "How often the Live page, the Dataflow page and the campaign pages refresh from the API.",
        "type": "int",
        "default": 2000,
        "min": 500,
        "max": 60000,
        "category": "Live",
        "unit": "ms",
    },
    {
        "key": "connection_poll_ms",
        "label": "Sidebar connection poll interval",
        "description": "How often the sidebar WhatsApp status dot refreshes.",
        "type": "int",
        "default": 5000,
        "min": 500,
        "max": 60000,
        "category": "Live",
        "unit": "ms",
    },
    {
        "key": "qr_poll_ms",
        "label": "QR panel poll interval",
        "description": "How often the dashboard re-captures the WhatsApp QR image while login is pending.",
        "type": "int",
        "default": 3000,
        "min": 500,
        "max": 30000,
        "category": "Live",
        "unit": "ms",
    },
    {
        "key": "dataflow_poll_ms",
        "label": "Dataflow poll interval",
        "description": "How often the Dataflow page fetches /live/db.",
        "type": "int",
        "default": 2000,
        "min": 500,
        "max": 30000,
        "category": "Live",
        "unit": "ms",
    },
    {
        "key": "scheduler_tick_seconds",
        "label": "Scheduler tick interval",
        "description": "How often the background scheduler checks for due campaigns. Lower is more responsive but busier.",
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 300,
        "category": "Campaigns",
        "unit": "seconds",
    },
    {
        "key": "retention_interval_hours",
        "label": "Retention cleanup interval",
        "description": "Minimum hours between automatic retention sweeps. The sweep itself runs on startup and after each interval elapses.",
        "type": "int",
        "default": 24,
        "min": 1,
        "max": 168,
        "category": "Data",
        "unit": "hours",
    },
    {
        "key": "retention_days",
        "label": "Keep logs and run history for",
        "description": "Delete logs, finished run history and debug files older than this many days. Analytics, campaign posts and all configuration are never deleted.",
        "type": "int",
        "default": 30,
        "min": 1,
        "max": 3650,
        "category": "Data",
        "unit": "days",
    },
    {
        "key": "message_retention_days",
        "label": "Keep captured messages for",
        "description": "Delete raw messages captured after your posts older than this many days. Spam-flagged or human-reviewed messages are always kept, and reports only store aggregates, so deleting raw rows never corrupts existing reports.",
        "type": "int",
        "default": 30,
        "min": 1,
        "max": 3650,
        "category": "Data",
        "unit": "days",
    },
    {
        "key": "keep_flagged_messages",
        "label": "Always keep flagged messages",
        "description": "Keep messages flagged as spam/scam (or marked reviewed) regardless of the capture retention window. Recommended on while the Market page builds your spam lexicon.",
        "type": "bool",
        "default": True,
        "category": "Data",
    },
    {
        "key": "max_group_misses",
        "label": "Silence group after consecutive misses",
        "description": "How many misses in a row a group may have before it is silenced and skipped by campaigns.",
        "type": "int",
        "default": config.MAX_GROUP_MISSES,
        "min": 1,
        "max": 1000,
        "category": "Groups",
        "unit": "misses",
    },
    {
        "key": "link_preview_delay",
        "label": "Link preview wait",
        "description": "Maximum seconds to wait for WhatsApp to build a link preview before sending.",
        "type": "int",
        "default": config.LINK_PREVIEW_DELAY,
        "min": 1,
        "max": 60,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "typing_delay_min",
        "label": "Typing delay (minimum)",
        "description": "Minimum pause between typed characters. Higher is slower and more human-like.",
        "type": "int",
        "default": config.TYPING_DELAY_MIN,
        "min": 1,
        "max": 500,
        "category": "Sending",
        "unit": "ms",
    },
    {
        "key": "typing_delay_max",
        "label": "Typing delay (maximum)",
        "description": "Maximum pause between typed characters.",
        "type": "int",
        "default": config.TYPING_DELAY_MAX,
        "min": 1,
        "max": 500,
        "category": "Sending",
        "unit": "ms",
    },
    {
        "key": "post_min_delay",
        "label": "Pause between posts (minimum)",
        "description": "Minimum wait after a successful post before the next target.",
        "type": "float",
        "default": config.POST_MIN_DELAY,
        "min": 0,
        "max": 600,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "post_max_delay",
        "label": "Pause between posts (maximum)",
        "description": "Maximum wait after a successful post before the next target.",
        "type": "float",
        "default": config.POST_MAX_DELAY,
        "min": 0,
        "max": 600,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "batch_pause_seconds",
        "label": "Pause between batches",
        "description": "How long to pause when a campaign moves to its next group batch.",
        "type": "float",
        "default": config.BATCH_PAUSE_SECONDS,
        "min": 0,
        "max": 600,
        "category": "Campaigns",
        "unit": "seconds",
    },
    {
        "key": "reply_capture_default_enabled",
        "label": "Capture replies by default (per campaign)",
        "description": "Default for the 'Capture replies' toggle on new campaigns. Campaigns can override it individually. Capture only starts after a confirmed-sent post, and never fails the post itself.",
        "type": "bool",
        "default": False,
        "category": "Campaigns",
    },
    {
        "key": "reply_capture_default_dwell",
        "label": "Capture dwell seconds",
        "description": "Default seconds to stay in the chat after a confirmed-sent post before scraping visible messages (replies, mentions, links). 0 captures immediately with no dwell.",
        "type": "float",
        "default": 30.0,
        "min": 0,
        "max": 600,
        "category": "Campaigns",
        "unit": "seconds",
    },
    {
        "key": "market_report_auto_weekly",
        "label": "Auto-generate weekly market report",
        "description": "When enabled, a market report is generated every Monday covering the previous week. Skipped automatically when no messages were captured that week.",
        "type": "bool",
        "default": False,
        "category": "Campaigns",
    },
    {
        "key": "search_wait",
        "label": "Wait after typing a search",
        "description": "How long to let WhatsApp filter results before reading them.",
        "type": "float",
        "default": config.SEARCH_WAIT,
        "min": 0,
        "max": 30,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "open_wait",
        "label": "Wait after opening a chat",
        "description": "How long to let a conversation load after clicking a search result.",
        "type": "float",
        "default": config.OPEN_WAIT,
        "min": 0,
        "max": 30,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "results_wait",
        "label": "Wait for search results",
        "description": "Extra seconds to let WhatsApp render the filtered results before reading them. 0 means read immediately (the default is usually fine).",
        "type": "float",
        "default": 0.0,
        "min": 0,
        "max": 30,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "compose_timeout",
        "label": "Compose box detect timeout",
        "description": "Maximum seconds to keep polling for the message composer after a chat is opened.",
        "type": "float",
        "default": 8.0,
        "min": 1,
        "max": 60,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "find_compose_wait",
        "label": "Compose box retry wait",
        "description": "Pause between attempts to find the message composer.",
        "type": "float",
        "default": config.FIND_COMPOSE_WAIT,
        "min": 0,
        "max": 30,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "after_typing_wait",
        "label": "Wait before sending",
        "description": "Final pause after typing and before pressing Enter.",
        "type": "float",
        "default": config.AFTER_TYPING_WAIT,
        "min": 0,
        "max": 30,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "send_confirm_wait",
        "label": "Send confirmation wait",
        "description": "How long to wait before checking that the message was sent.",
        "type": "float",
        "default": config.SEND_CONFIRM_WAIT,
        "min": 0,
        "max": 30,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "retry_delay",
        "label": "Retry delay",
        "description": "Base pause before retrying a failed search or open. Grows by one second per retry attempt.",
        "type": "float",
        "default": config.RETRY_DELAY,
        "min": 0,
        "max": 60,
        "category": "Navigation",
        "unit": "seconds",
    },
    {
        "key": "preview_grace_wait",
        "label": "Link preview grace wait",
        "description": "Extra seconds after the link preview is missing before sending anyway. 0 sends immediately.",
        "type": "float",
        "default": 0.6,
        "min": 0,
        "max": 30,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "preview_extra_wait",
        "label": "Link preview extra wait",
        "description": "Composed-message fallback: seconds to wait longer when no preview appeared within the regular wait before sending.",
        "type": "float",
        "default": 2.0,
        "min": 0,
        "max": 60,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "send_fallback_wait",
        "label": "Send button fallback wait",
        "description": "Seconds to wait after clicking the send button when Enter did not empty the compose box.",
        "type": "float",
        "default": 1.5,
        "min": 0,
        "max": 30,
        "category": "Sending",
        "unit": "seconds",
    },
    {
        "key": "detailed_logs",
        "label": "Detailed step logs",
        "description": "Write every search/group/composer/typing/send step to the Logs table and Live feed.",
        "type": "bool",
        "default": True,
        "category": "Diagnostics",
    },
    {
        "key": "debug_capture",
        "label": "Capture failures",
        "description": "Save a screenshot and the page DOM in data/debug/ whenever a target fails.",
        "type": "bool",
        "default": True,
        "category": "Diagnostics",
    },
    {
        "key": "trace_files",
        "label": "Write per-target trace files",
        "description": "Write the full step trace, including the complete message text, to data/debug/trace_*.log.",
        "type": "bool",
        "default": True,
        "category": "Diagnostics",
    },
]

_BY_KEY: Dict[str, Dict[str, Any]] = {entry["key"]: entry for entry in SETTINGS}


def _coerce(entry: Dict[str, Any], value: Any) -> Any:
    """Convert and clamp one value according to its setting definition."""
    kind = entry.get("type", "str")
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if kind == "int":
        number: Any = int(float(value))
    elif kind == "float":
        number = float(value)
    else:
        return str(value)
    if entry.get("min") is not None:
        number = max(entry["min"], number)
    if entry.get("max") is not None:
        number = min(entry["max"], number)
    return number


def get_values() -> Dict[str, Any]:
    """Return every setting's current value, falling back to its default."""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_meta").fetchall()
    conn.close()
    stored = {row["key"]: row["value"] for row in rows}
    values: Dict[str, Any] = {}
    for entry in SETTINGS:
        raw = stored.get(entry["key"])
        if raw is None or raw == "":
            values[entry["key"]] = entry["default"]
            continue
        try:
            values[entry["key"]] = _coerce(entry, raw)
        except (TypeError, ValueError):
            values[entry["key"]] = entry["default"]
    return values


def get_schema() -> List[Dict[str, Any]]:
    return [dict(entry) for entry in SETTINGS]


def get_stored(key: str) -> Any:
    """Return only the persisted value, or None when the user never set it.

    Callers that have their own fallback (for example the tests overriding the
    module-level ``MAX_GROUP_MISSES``) use this instead of ``get_setting``.
    """
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row or row["value"] in (None, ""):
        return None
    entry = _BY_KEY.get(key)
    if entry is None:
        return row["value"]
    try:
        return _coerce(entry, row["value"])
    except (TypeError, ValueError):
        return None


def get_setting(key: str, default: Any = None) -> Any:
    return get_values().get(key, default)


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    value = get_setting(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ── non-schema app_meta counters ────────────────────────────────────────


def get_meta_int(key: str, default: int = 0) -> int:
    """Read an internal integer counter from app_meta (not shown in the UI)."""
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row or row["value"] in (None, ""):
        return default
    try:
        return int(float(row["value"]))
    except (TypeError, ValueError):
        return default


def set_meta_int(key: str, value: int) -> int:
    """Persist an internal integer counter in app_meta."""
    number = int(value)
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(number)),
    )
    conn.commit()
    conn.close()
    return number


def update_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a partial mapping of setting key -> value and return all values."""
    cleaned: Dict[str, Any] = {}
    for key, value in payload.items():
        entry = _BY_KEY.get(key)
        if entry is None:
            raise ValueError(f"unknown setting '{key}'")
        cleaned[key] = _coerce(entry, value)

    if cleaned:
        conn = get_conn()
        for key, value in cleaned.items():
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
        conn.commit()
        conn.close()
        log(
            "info",
            "settings updated: " + ", ".join(f"{key}={value}" for key, value in cleaned.items()),
            "settings",
        )
    return get_values()
