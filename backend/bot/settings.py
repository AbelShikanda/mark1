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
        "description": "Clear the saved WhatsApp profile and show a fresh QR code after this many campaign runs. 1 means every run asks for a QR.",
        "type": "int",
        "default": 1,
        "min": 1,
        "max": 100,
        "category": "Session",
        "unit": "runs",
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
        "description": "Base pause before retrying a failed search or open.",
        "type": "float",
        "default": config.RETRY_DELAY,
        "min": 0,
        "max": 60,
        "category": "Navigation",
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
