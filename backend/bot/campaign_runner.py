"""Campaign execution engine.

Behaviour:
- a campaign targets one group/client, *all* groups/clients, or the live union
  of reusable group batches, in batches; one run keeps looping the batches
  until the whole cycle is covered, and a cursor carries any remainder into the
  next run;
- products are fixed or auto-picked with equitable category rotation;
- a fixed product is ``isPending`` while scheduled and becomes ``isPosted``
  only after the target cycle completes (or a single-target run succeeds);
- repeat campaigns re-run daily/weekly/monthly; rePost allows a posted product
  to be posted again;
- link campaigns use only "my groups" that have a link and never target core
  groups (core links are prioritised as sources);
- a busy campaign is pushed to the next free slot instead of retried forever;
- images are attached to the WhatsApp message when the product has media.
"""

from __future__ import annotations

import random
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from config import (
    BATCH_PAUSE_SECONDS,
    MAX_GROUP_FAILURES,
    MAX_GROUP_MISSES,
    SESSION_DIR,
)
from db_logic import get_conn, log
from scheduling import (
    advance_after_run,
    clear_pending_if_unused,
    defer_campaign,
    refresh_pending_products,
    set_campaign_pending_product,
    sync_campaign_schedule,
)
from . import run_state, settings as app_settings
from .capture import capture_post_replies
from .live_state import get_connection_state, update_connection_state
from .login_manager import WhatsAppBot
from .poster import post_product, post_text

_bot: Optional[WhatsAppBot] = None
_bot_lock = threading.Lock()
_cancel_lock = threading.Lock()
_cancel_events: Dict[int, threading.Event] = {}


# ── bot lifecycle ───────────────────────────────────────────────────────


def _force_kill_browser_processes_linux() -> int:
    """Linux branch: SIGKILL Chromium/headless_shell processes using our profile."""
    killed = 0
    try:
        out = subprocess.run(
            ["pgrep", "-f", "whatsapp_session"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception as exc:
        log("warning", f"pgrep failed: {exc}", "campaign_runner")
        return 0
    import os
    import signal

    for line in out.splitlines():
        pid_s = line.strip()
        if not pid_s.isdigit():
            continue
        pid = int(pid_s)
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
        except Exception as exc:
            log("warning", f"kill pid {pid} failed: {exc}", "campaign_runner")
    if killed:
        log("info", f"force-killed {killed} browser process(es)", "campaign_runner")
    return killed


def force_kill_browser_processes() -> int:
    """Hard-kill Chromium/headless_shell processes for this app's profile.

    A graceful Playwright ``context.close()`` can hang indefinitely while a
    page is mid-navigation, so the Stop button must not depend on it: match
    browser processes whose command line references our WhatsApp profile
    directory and taskkill them immediately.
    """
    marker = str(SESSION_DIR).lower().replace("\\", "/")

    if sys.platform.startswith("linux"):
        return _force_kill_browser_processes_linux()

    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -match 'chrome|headless_shell|chromium') -and $_.CommandLine } | "
        "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception as exc:
        log("warning", f"could not enumerate browser processes: {exc}", "campaign_runner")
        return 0
    killed = 0
    seen = set()
    for line in out.splitlines():
        pid_s, _, cmdline = line.partition("|")
        pid_s = pid_s.strip()
        if not pid_s.isdigit() or int(pid_s) in seen:
            continue
        cmd_norm = (cmdline or "").lower().replace("\\", "/")
        if "whatsapp_session" not in cmd_norm and marker not in cmd_norm:
            continue
        seen.add(int(pid_s))
        try:
            subprocess.run(
                ["taskkill", "/PID", pid_s, "/T", "/F"],
                capture_output=True, timeout=15,
            )
            killed += 1
        except Exception as exc:
            log("warning", f"taskkill pid {pid_s} failed: {exc}", "campaign_runner")
    if killed:
        log("info", f"force-killed {killed} browser process(es)", "campaign_runner")
    return killed


def get_bot(headless: bool = False) -> WhatsAppBot:
    """Return a started bot.

    The lock is only held while assigning the instance: starting Playwright
    and waiting for a manual QR login can take minutes, and a cancel request
    must never block behind that wait.
    """
    global _bot
    with _bot_lock:
        bot = _bot
        if bot is None:
            bot = WhatsAppBot(headless=headless)
            _bot = bot
        else:
            return bot

    try:
        bot.start()
        bot.navigate()
    except Exception:
        with _bot_lock:
            if _bot is bot:
                _bot = None
        try:
            bot.stop()
        except Exception:
            pass
        raise
    return bot


def stop_bot() -> None:
    global _bot
    with _bot_lock:
        bot = _bot
        _bot = None
    if bot is not None:
        try:
            bot.stop()
        except Exception:
            pass
    # Whatever the graceful stop managed, make sure no Chromium process keeps
    # running against the shared profile: Stop must not depend on a cooperative
    # page that may be stuck mid-navigation.
    force_kill_browser_processes()


# ── session lifecycle (QR after N runs) ─────────────────────────────────

SESSION_RUNS_KEY = "session_runs_used"


def _session_dir_has_files() -> bool:
    try:
        return SESSION_DIR.exists() and any(SESSION_DIR.iterdir())
    except Exception:
        return False


def clear_session_dir() -> None:
    """Delete the persisted WhatsApp profile so the next launch shows a QR."""
    try:
        shutil.rmtree(SESSION_DIR, ignore_errors=True)
    except Exception:
        pass
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _browser_open_state() -> Dict[str, Any]:
    with _bot_lock:
        bot = _bot
    state = get_connection_state()
    headless = bot.headless if bot is not None else app_settings.get_bool("headless", False)
    return {
        "state": state.get("state"),
        "qr_visible": bool(state.get("qr_visible")),
        "headless": bool(headless),
        "browser_open": bool(bot is not None and not bot.is_browser_closed()),
    }


def session_status() -> Dict[str, Any]:
    limit = max(1, app_settings.get_int("qr_after_logins", 1))
    used = max(0, app_settings.get_meta_int(SESSION_RUNS_KEY, 0))
    return {
        "used": used,
        "limit": limit,
        "session_exists": _session_dir_has_files(),
        "connected": _browser_open_state()["state"] == "connected",
        "ever_connected": bool(app_settings.get_meta_int("whatsapp_ever_connected", 0)),
        **_browser_open_state(),
    }


def session_qr() -> Dict[str, Any]:
    """Snapshot of the login flow for the dashboard QR panel."""
    with _bot_lock:
        bot = _bot
    state = get_connection_state()
    waiting = bool(state.get("qr_visible")) or state.get("state") in ("waiting_qr", "waiting_login")
    data_url = bot.qr_data_url() if (bot is not None and waiting) else None
    if bot is None:
        message = "No WhatsApp browser is running. Start a campaign run; the QR code will appear here."
    elif data_url:
        message = (
            "QR captured from the hidden browser."
            if bot.headless
            else "Browser is visible; scan the QR code in the window."
        )
    elif waiting:
        message = "Waiting for the QR code to render in WhatsApp Web…"
    else:
        message = "A QR code is only available while WhatsApp needs to log in."
    return {
        "available": bool(data_url) or waiting,
        "qr_data_url": data_url,
        "message": message,
        "headless": bool(bot.headless) if bot is not None else app_settings.get_bool("headless", False),
        "browser_open": bool(bot is not None and not bot.is_browser_closed()),
        "state": state.get("state"),
    }


def show_browser() -> Dict[str, Any]:
    """Temporarily switch a hidden session to a visible window for scanning."""
    with _bot_lock:
        bot = _bot
    if bot is None:
        return {
            "ok": True,
            "message": (
                "No WhatsApp browser is running. A run will open one automatically; "
                "when headless, the QR appears in the dashboard."
            ),
            "browser_open": False,
            "headless": app_settings.get_bool("headless", False),
        }
    if not bot.headless:
        return {
            "ok": True,
            "message": "The browser window is already visible.",
            "browser_open": not bot.is_browser_closed(),
            "headless": False,
        }
    ok = bot.switch_to_headed_for_qr()
    return {
        "ok": ok,
        "message": (
            "Opened a visible WhatsApp browser; scan the QR code in the window "
            "(it also appears on the Live page)."
            if ok
            else "Could not open a visible window. The QR on the Live page still works."
        ),
        "browser_open": not bot.is_browser_closed(),
        "headless": bot.headless,
    }


def use_headless() -> Dict[str, Any]:
    """Persist headless mode and relaunch the live session hidden."""
    try:
        app_settings.update_settings({"headless": True})
    except Exception as exc:  # settings write failed; still report gracefully
        log("warning", f"could not persist headless setting: {exc}", "whatsapp")
    with _bot_lock:
        bot = _bot
    ok = True
    if bot is not None and not bot.headless:
        ok = bot.relaunch_headless()
    return {
        "ok": ok,
        "message": (
            "Switched WhatsApp to headless mode."
            if ok
            else "Headless relaunch failed; the visible window was kept open."
        ),
        "browser_open": bool(bot is not None and not bot.is_browser_closed()),
        "headless": True,
    }


def use_headed() -> Dict[str, Any]:
    """Persist visible-browser mode and relaunch the live session in a window."""
    try:
        app_settings.update_settings({"headless": False})
    except Exception as exc:  # settings write failed; still report gracefully
        log("warning", f"could not persist headed setting: {exc}", "whatsapp")
    with _bot_lock:
        bot = _bot
    ok = True
    if bot is not None and bot.headless:
        ok = bot.relaunch_headed()
    return {
        "ok": ok,
        "message": (
            "Switched WhatsApp to a visible browser window."
            if ok
            else "Visible-window relaunch failed; the hidden browser was kept open."
        ),
        "browser_open": bool(bot is not None and not bot.is_browser_closed()),
        "headless": False,
    }


def reset_session() -> Dict[str, Any]:
    """Forget the saved profile and force a QR scan on the next campaign run."""
    stop_bot()
    clear_session_dir()
    app_settings.set_meta_int(SESSION_RUNS_KEY, 0)
    app_settings.set_meta_int("whatsapp_ever_connected", 0)
    try:
        update_connection_state("stopped", "Saved session cleared; QR required")
    except Exception:
        pass
    log("info", "[session] reset requested; QR required on next run", "poster")
    return session_status()


def prepare_session_for_run() -> Dict[str, Any]:
    """Decide whether this run reuses the saved profile or asks for a QR.

    ``qr_after_logins`` counts campaign runs between QR scans. With the default
    (1) every run clears the profile and shows a fresh QR. With N=2 the profile
    is reused for the second run, then cleared before the third.
    """
    limit = max(1, app_settings.get_int("qr_after_logins", 1))
    used = max(0, app_settings.get_meta_int(SESSION_RUNS_KEY, 0))
    cleared = False

    if limit <= 1 or used >= limit:
        stop_bot()
        clear_session_dir()
        app_settings.set_meta_int(SESSION_RUNS_KEY, 0)
        cleared = True
        try:
            update_connection_state("stopped", "Session cleared; QR required")
        except Exception:
            pass
        log("info", "[session] session cleared; QR required", "poster")
    else:
        log("info", f"[session] using saved session ({used}/{limit})", "poster")

    return {"limit": limit, "used": used, "cleared": cleared}


def pair_headed_for_run(campaign_id: int) -> bool:
    """Open a visible browser so the user can scan the QR, then close it.

    Used when the configured mode is headless but WhatsApp needs a fresh
    pairing: headless hides the QR, so we pop a real window, wait for the
    scan, close it, and let the run relaunch hidden with the saved session.
    """
    cancel_event = _event_for(campaign_id)
    log("info", f"campaign {campaign_id}: opening visible browser for WhatsApp pairing", "campaign_runner")
    bot = WhatsAppBot(headless=False)
    bot.cancel_event = cancel_event
    try:
        bot.start()
        update_connection_state("loading", "Loading WhatsApp Web")
        bot.page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)
        ok = bot.wait_for_pairing()
    except Exception as exc:
        log("error", f"campaign {campaign_id}: pairing browser failed: {exc}", "campaign_runner")
        ok = False
    finally:
        try:
            bot.stop()
        except Exception:
            pass
    if ok:
        app_settings.set_meta_int("whatsapp_ever_connected", 1)
        log("info", f"campaign {campaign_id}: WhatsApp paired; pairing window closed", "campaign_runner")
    else:
        log("warning", f"campaign {campaign_id}: WhatsApp pairing did not complete", "campaign_runner")
    return ok


# ── product selection ───────────────────────────────────────────────────


def reset_products_if_all_posted() -> None:
    conn = get_conn()
    rows = conn.execute("SELECT id, status FROM products").fetchall()
    if not rows:
        conn.close()
        return
    reset = all(r["status"] == "isPosted" for r in rows)
    if reset:
        conn.execute("UPDATE products SET status = 'isNotPosted', posted_at = NULL, updated_at = datetime('now')")
        conn.commit()
        log("info", "all products posted; reset all to isNotPosted", "campaign_runner")
        scheduled = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM campaigns WHERE next_run_at IS NOT NULL "
                "AND product_id IS NOT NULL AND auto_product = 0"
            ).fetchall()
        ]
    else:
        scheduled = []
    conn.close()
    # A campaign that is already scheduled for a future run should keep its
    # fixed product marked isPending across the reset.
    for campaign_id in scheduled:
        set_campaign_pending_product(campaign_id)


def pick_equitable_random_product(rePost: bool = False) -> Optional[Dict[str, Any]]:
    """Pick an unposted product, preferring the category that is least complete."""
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()]
    conn.close()
    if not rows:
        return None

    candidates = [r for r in rows if r["status"] != "isPosted"]
    if not candidates:
        if not rePost:
            return None
        posted = [r for r in rows if r["status"] == "isPosted"]
        if not posted:
            return None
        posted.sort(key=lambda r: r.get("last_posted_at") or "")
        return posted[0]

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for item in candidates:
        by_category.setdefault(item.get("category") or "__none__", []).append(item)

    totals: Dict[str, int] = {}
    posted_counts: Dict[str, int] = {}
    for item in rows:
        cat = item.get("category") or "__none__"
        totals[cat] = totals.get(cat, 0) + 1
        if item["status"] == "isPosted":
            posted_counts[cat] = posted_counts.get(cat, 0) + 1

    def score(cat: str) -> float:
        return posted_counts.get(cat, 0) / max(1, totals.get(cat, 1))

    least_complete = min(by_category.keys(), key=lambda c: (score(c), -len(by_category[c])))
    return random.choice(by_category[least_complete])


def mark_product_pending(pid: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE products SET status = 'isPending', updated_at = datetime('now') "
        "WHERE id = ? AND status = 'isNotPosted'",
        (pid,),
    )
    conn.commit()
    conn.close()


def mark_product_posted(pid: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE products SET status = 'isPosted', posted_at = datetime('now'), "
        "last_posted_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
        (pid,),
    )
    conn.commit()
    conn.close()


# ── group caps / failures ───────────────────────────────────────────────


def can_post_to_group(group: Dict[str, Any], repost: bool = False) -> bool:
    """Daily-cap gate.

    The per-group daily cap is only bypassed by campaigns with
    "Re-post even if already posted" enabled; active/silenced state is
    always enforced.
    """
    if not bool(group.get("is_active", 1)) or bool(group.get("is_silenced", 0)):
        return False
    if repost:
        return True
    return group["isPostedProductToday"] < max(1, group["n"])


def mark_group_posted(group_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE groups SET isPostedProductToday = isPostedProductToday + 1 WHERE id = ?",
        (group_id,),
    )
    conn.commit()
    conn.close()


SETTINGS_MAX_GROUP_MISSES = "max_group_misses"


def get_max_group_misses() -> int:
    """The live silence threshold: dashboard setting first, env fallback second."""
    stored = app_settings.get_stored(SETTINGS_MAX_GROUP_MISSES)
    if stored is not None:
        try:
            return max(1, int(stored))
        except (TypeError, ValueError):
            pass
    return max(1, int(MAX_GROUP_MISSES))


def set_max_group_misses(value: int) -> int:
    threshold = max(1, min(1000, int(value)))
    app_settings.update_settings({SETTINGS_MAX_GROUP_MISSES: threshold})
    return threshold


def record_group_failure(
    group_id: int,
    reason: str = "",
    *,
    run_id: Optional[int] = None,
    campaign_id: Optional[int] = None,
    target_name: Optional[str] = None,
) -> str:
    """Record one miss. Returns "skipped" | "failed" | "silenced" | "not_found".

    ``failures`` is the consecutive-miss counter; ``total_misses`` is lifetime.
    Silence (not the manual ``is_active`` flag) is what excludes a group after
    repeated misses.

    A target whose post failed while the user asked to skip it is a skip, not
    a miss: it must not count toward failure streaks or silencing. The target
    result is recorded as "skipped" before returning "skipped".
    """
    # A target whose post failed while the user asked to skip it is a skip,
    # not a miss: it must not count toward failure streaks or silencing.
    if campaign_id and run_id and run_state.skip_requested(campaign_id):
        log(
            "info",
            f"group {group_id} post failed with a skip requested; recording as skipped, not missed",
            "campaign_runner",
        )
        run_state.clear_skip(campaign_id)
        run_state.record_target_result(
            run_id, "group", group_id, "skipped", "Skipped by user",
            target_name=target_name, campaign_id=campaign_id,
        )
        return "skipped"
    conn = get_conn()
    row = conn.execute(
        "SELECT name, failures, total_misses, is_silenced, is_active "
        "FROM groups WHERE id = ?",
        (group_id,),
    ).fetchone()
    if not row:
        conn.close()
        if reason:
            log("warning", f"group {group_id} failed: {reason} (group not found)", "campaign_runner")
        return "not_found"
    name = target_name or row["name"] or f"group {group_id}"
    failures = int(row["failures"] or 0) + 1
    total_misses = int(row["total_misses"] or 0) + 1
    threshold = get_max_group_misses()
    should_silence = failures >= threshold and not bool(row["is_silenced"])
    if should_silence:
        conn.execute(
            "UPDATE groups SET failures = ?, total_misses = ?, last_missed_at = datetime('now'), "
            "is_silenced = 1, silenced_at = datetime('now'), silence_reason = ? WHERE id = ?",
            (failures, total_misses, f"auto: {failures} misses", group_id),
        )
    else:
        conn.execute(
            "UPDATE groups SET failures = ?, total_misses = ?, last_missed_at = datetime('now') "
            "WHERE id = ?",
            (failures, total_misses, group_id),
        )
    conn.commit()
    conn.close()

    if reason:
        log("warning", f"group '{name}' missed ({failures}): {reason}", "campaign_runner")
    if should_silence:
        message = (
            f"Group '{name}' silenced after {failures} consecutive misses "
            f"(reason: {reason or 'post failed'})"
        )
        log("error", message, "campaign_runner")
        run_state.record_event(
            run_id,
            "error",
            "group_silenced",
            message,
            target_type="group",
            target_id=group_id,
            target_name=name,
            campaign_id=campaign_id,
        )
    return "silenced" if should_silence else "failed"


def record_group_success(
    group_id: int,
    *,
    run_id: Optional[int] = None,
    campaign_id: Optional[int] = None,
) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE groups SET failures = 0, last_success_at = datetime('now') WHERE id = ?",
        (group_id,),
    )
    conn.commit()
    conn.close()


def reset_daily_group_counts() -> None:
    """Reset the per-group daily counter once per calendar day."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'last_group_reset'").fetchone()
    if row and row["value"] == today:
        conn.close()
        return
    conn.execute("UPDATE groups SET isPostedProductToday = 0")
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('last_group_reset', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (today,),
    )
    conn.commit()
    conn.close()


# ── campaign claiming / cancellation ───────────────────────────────────


def try_claim_campaign(cid: int) -> bool:
    """Atomically mark one campaign as running, refusing if another is running."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        running = conn.execute(
            "SELECT id FROM campaigns WHERE status = 'isRunning' LIMIT 1"
        ).fetchone()
        if running:
            conn.rollback()
            return False
        cur = conn.execute(
            "UPDATE campaigns SET status = 'isRunning' WHERE id = ? AND status != 'isRunning'",
            (cid,),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _event_for(cid: int) -> threading.Event:
    with _cancel_lock:
        return _cancel_events.setdefault(cid, threading.Event())


def clear_cancel(cid: int) -> None:
    with _cancel_lock:
        event = _cancel_events.get(cid)
        if event:
            event.clear()


def is_cancelled(cid: int) -> bool:
    with _cancel_lock:
        event = _cancel_events.get(cid)
        return bool(event and event.is_set())


def cancel_campaign(cid: int) -> None:
    """Request cancellation.

    A running campaign keeps ``isRunning`` until its runner thread actually
    exits, so a second campaign cannot be claimed into the same bot session.
    """
    _event_for(cid).set()
    conn = get_conn()
    row = conn.execute("SELECT status FROM campaigns WHERE id = ?", (cid,)).fetchone()
    if row and row["status"] == "isRunning":
        conn.close()
        log("info", f"campaign {cid} stop requested", "campaign_runner")
        return
    conn.execute("UPDATE campaigns SET status = 'isPosted', next_run_at = NULL WHERE id = ?", (cid,))
    conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
    conn.commit()
    conn.close()
    log("info", f"campaign {cid} cancelled", "campaign_runner")


def is_any_campaign_running() -> bool:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) AS c FROM campaigns WHERE status = 'isRunning'").fetchone()
    conn.close()
    return bool(row and row["c"] > 0)


def get_busy_recommendation() -> str:
    return (
        "Another campaign is running. This one will be moved to the next free "
        "slot; you can also stop the running campaign first."
    )


# ── batching ────────────────────────────────────────────────────────────


def _meta_get(key: str) -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    try:
        return int(row["value"]) if row and row["value"] is not None else 0
    except (TypeError, ValueError):
        return 0


def _meta_set(key: str, value: int) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def _batch_select(
    rows: List[Dict[str, Any]],
    limit: int,
    cursor: int,
) -> tuple[List[Dict[str, Any]], int]:
    """Pure batch selection: (selected rows, next cursor).

    Kept side-effect free so the live preview can simulate the cursor without
    writing to ``app_meta``. ``_batch`` is the only caller that persists the
    returned cursor.
    """
    if limit <= 0 or limit >= len(rows):
        return list(rows), 0

    ordered = sorted(rows, key=lambda r: r["id"])
    upcoming = [r for r in ordered if r["id"] > cursor]
    if not upcoming:
        # A full cycle has been covered - start a new one.
        upcoming = ordered
    if len(upcoming) <= limit:
        # Never wrap inside the last batch: finish the cycle cleanly so no
        # group is repeated before every group has been covered.
        return upcoming[:limit], 0
    selected = upcoming[:limit]
    return selected, selected[-1]["id"]


def _batch(rows: List[Dict[str, Any]], campaign: Dict[str, Any], cursor_key: str) -> List[Dict[str, Any]]:
    """Take the next batch after the stored cursor, wrapping at the end."""
    limit = int(campaign.get("batch_size") or 0)
    cursor = _meta_get(cursor_key)
    selected, next_cursor = _batch_select(rows, limit, cursor)
    _meta_set(cursor_key, next_cursor)
    return selected[:limit] if limit > 0 else selected


def _batch_scope_groups(
    campaign: Dict[str, Any],
    exclude_core: bool = False,
    exclude_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Active groups that belong to the campaign's selected live batches.

    Membership is resolved on every call, so editing a batch immediately
    affects every campaign that references it. Duplicate groups across batches
    collapse to one row via ``GROUP BY g.id``.
    """
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT g.* FROM groups g "
        "JOIN group_batch_members m ON m.group_id = g.id "
        "JOIN campaign_group_batches cgb ON cgb.batch_id = m.batch_id "
        "WHERE cgb.campaign_id = ? AND g.is_active = 1 "
        "AND COALESCE(g.is_silenced, 0) = 0 "
        "GROUP BY g.id ORDER BY g.id",
        (campaign["id"],),
    ).fetchall()]
    conn.close()
    eligible = []
    for group in rows:
        if exclude_core and group.get("is_core"):
            continue
        if exclude_name and (group.get("name") or "").strip().lower() == exclude_name.strip().lower():
            continue
        eligible.append(group)
    return eligible


def _cycle_complete(cid: int, kind: str, campaign: Dict[str, Any]) -> bool:
    """True when there is no next fresh batch to run.

    ``_batch`` resets the cursor to 0 when it serves the final batch. Campaigns
    that do not batch (a single target, or all targets at once) are complete
    after one pass even if an old cursor from a previous configuration exists.
    """
    if kind == "group":
        scope = campaign.get("target_scope")
        if scope == "batch":
            # The pool is resolved live from the selected batches. If it has
            # one group, or batch_size covers it in one pass, there is no
            # further batch to run this cycle.
            pool_size = len(_batch_scope_groups(campaign))
            limit = int(campaign.get("batch_size") or 0)
            if pool_size <= 1 or limit <= 0 or limit >= pool_size:
                return True
        elif scope != "all":
            return True
    else:
        if campaign.get("target_scope") != "all":
            conn = get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM campaign_clients WHERE campaign_id = ?",
                (cid,),
            ).fetchone()
            conn.close()
            selected = int(row["c"] if row else 0)
            limit = int(campaign.get("batch_size") or 0)
            if selected <= 1 or limit <= 0 or limit >= selected:
                return True
    return _meta_get(f"campaign:{cid}:{kind}_cursor") == 0


def _run_paced_batches(
    cid: int,
    campaign: Dict[str, Any],
    run_once,
    kind: str,
    run_id: Optional[int] = None,
) -> tuple[int, bool]:
    """Run batches until the whole cycle is covered, pacing between chunks.

    ``batch_size`` is a pacing control (targets per chunk), not a limit that
    silently drops the rest of the groups. A one-shot "all groups" campaign
    therefore always reaches every group.
    """
    total = 0
    while not is_cancelled(cid):
        run_state.set_run_phase(run_id, status="running", phase="batch_starting")
        sent = run_once()
        total += sent
        if sent <= 0:
            break
        if _cycle_complete(cid, kind, campaign):
            break
        pause = max(0.0, app_settings.get_float("batch_pause_seconds", BATCH_PAUSE_SECONDS)) + random.uniform(0, 2)
        run_state.set_run_phase(run_id, status="running", phase="waiting_batch")
        deadline = time.monotonic() + pause
        while time.monotonic() < deadline and not is_cancelled(cid):
            time.sleep(0.5)
    complete = _cycle_complete(cid, kind, campaign)
    if run_id:
        run_state.set_run_phase(run_id, cycle_complete=complete)
    return total, complete


def pick_group_batch(campaign: Dict[str, Any], exclude_core: bool = False, exclude_name: Optional[str] = None) -> List[Dict[str, Any]]:
    # A "batch" campaign targets the live union of its selected batches. The
    # join/dedupe happens on every call, so membership changes are picked up
    # by the next run without touching the campaign.
    if campaign.get("target_scope") == "batch":
        pool = [
            g for g in _batch_scope_groups(campaign, exclude_core, exclude_name)
            if can_post_to_group(g, repost=bool(campaign.get("rePost")))
        ]
        if not pool:
            return []
        cursor_key = f"campaign:{campaign['id']}:group_cursor"
        if len(pool) == 1:
            _meta_set(cursor_key, 0)
            return pool
        return _batch(pool, campaign, cursor_key)

    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM groups WHERE is_active = 1 AND COALESCE(is_silenced, 0) = 0 ORDER BY id"
    ).fetchall()]
    conn.close()
    eligible = []
    for group in rows:
        if exclude_core and group.get("is_core"):
            continue
        if exclude_name and (group.get("name") or "").strip().lower() == exclude_name.strip().lower():
            continue
        if can_post_to_group(group, repost=bool(campaign.get("rePost"))):
            eligible.append(group)
    if not eligible:
        return []
    if campaign.get("target_scope") == "all":
        return _batch(eligible, campaign, f"campaign:{campaign['id']}:group_cursor")
    if not campaign.get("group_id"):
        return []
    return [g for g in eligible if g["id"] == campaign["group_id"]]


def pick_client_batch(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM clients ORDER BY id").fetchall()]
    selected = [
        r["client_id"]
        for r in conn.execute(
            "SELECT client_id FROM campaign_clients WHERE campaign_id = ? ORDER BY client_id",
            (campaign["id"],),
        ).fetchall()
    ]
    conn.close()
    if not rows:
        return []
    if campaign.get("target_scope") == "all":
        pool = rows
    elif selected:
        wanted = set(selected)
        pool = [c for c in rows if c["id"] in wanted]
    elif campaign.get("client_id"):
        pool = [c for c in rows if c["id"] == campaign["client_id"]]
    else:
        return []
    if len(pool) <= 1:
        return pool
    return _batch(pool, campaign, f"campaign:{campaign['id']}:client_cursor")


def _preview_group_pool(
    campaign: Dict[str, Any],
    exclude_core: bool = False,
    exclude_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """The same live pool ``pick_group_batch`` would use, without picking."""
    if campaign.get("target_scope") == "batch":
        return [
            g for g in _batch_scope_groups(campaign, exclude_core, exclude_name)
            if can_post_to_group(g, repost=bool(campaign.get("rePost")))
        ]

    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM groups WHERE is_active = 1 AND COALESCE(is_silenced, 0) = 0 ORDER BY id"
    ).fetchall()]
    conn.close()
    eligible = []
    for group in rows:
        if exclude_core and group.get("is_core"):
            continue
        if exclude_name and (group.get("name") or "").strip().lower() == exclude_name.strip().lower():
            continue
        if can_post_to_group(group, repost=bool(campaign.get("rePost"))):
            eligible.append(group)
    if campaign.get("target_scope") == "all":
        return eligible
    if not campaign.get("group_id"):
        return []
    return [g for g in eligible if g["id"] == campaign["group_id"]]


def _preview_client_pool(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM clients ORDER BY id").fetchall()]
    selected = [
        r["client_id"]
        for r in conn.execute(
            "SELECT client_id FROM campaign_clients WHERE campaign_id = ? ORDER BY client_id",
            (campaign["id"],),
        ).fetchall()
    ]
    conn.close()
    if not rows:
        return []
    if campaign.get("target_scope") == "all":
        return rows
    if selected:
        wanted = set(selected)
        return [c for c in rows if c["id"] in wanted]
    if campaign.get("client_id"):
        return [c for c in rows if c["id"] == campaign["client_id"]]
    return []


def _cycle_already_started(campaign: Dict[str, Any], target_type: str, run_id: Optional[int]) -> bool:
    conn = get_conn()
    if run_id:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM campaign_run_targets WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM campaign_run_targets WHERE campaign_id = ? AND target_type = ?",
            (campaign["id"], target_type),
        ).fetchone()
    conn.close()
    return bool(row and int(row["c"]) > 0)


def preview_remaining_groups(
    campaign: Dict[str, Any],
    exclude_core: bool = False,
    exclude_name: Optional[str] = None,
    *,
    run_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Read-only preview of group chunks after the current cursor.

    Mirrors ``pick_group_batch``/``_batch`` exactly but never writes to
    ``app_meta``. Single-target scopes, and campaigns whose batch size covers
    the whole pool, have no future chunk.
    """
    if campaign.get("campaign_type") == "product_client":
        return preview_remaining_clients(campaign, run_id=run_id)
    if campaign.get("target_scope") not in ("all", "batch"):
        return []

    pool = _preview_group_pool(campaign, exclude_core, exclude_name)
    limit = int(campaign.get("batch_size") or 0)
    if not pool or limit <= 0 or limit >= len(pool):
        return []

    cursor_key = f"campaign:{campaign['id']}:group_cursor"
    cursor = _meta_get(cursor_key)
    if cursor == 0 and _cycle_already_started(campaign, "group", run_id):
        return []

    result: List[Dict[str, Any]] = []
    guard = 0
    while guard < 500:
        guard += 1
        selected, next_cursor = _batch_select(pool, limit, cursor)
        if not selected:
            break
        result.extend(
            {
                "target_type": "group",
                "target_id": g["id"],
                "target_name": g.get("name"),
                "batch_no": None,
            }
            for g in selected
        )
        if next_cursor == 0:
            break
        cursor = next_cursor
    return result


def preview_remaining_clients(
    campaign: Dict[str, Any],
    *,
    run_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if campaign.get("target_scope") != "all":
        return []
    pool = _preview_client_pool(campaign)
    limit = int(campaign.get("batch_size") or 0)
    if not pool or limit <= 0 or limit >= len(pool):
        return []

    cursor_key = f"campaign:{campaign['id']}:client_cursor"
    cursor = _meta_get(cursor_key)
    if cursor == 0 and _cycle_already_started(campaign, "client", run_id):
        return []

    result: List[Dict[str, Any]] = []
    guard = 0
    while guard < 500:
        guard += 1
        selected, next_cursor = _batch_select(pool, limit, cursor)
        if not selected:
            break
        result.extend(
            {
                "target_type": "client",
                "target_id": c["id"],
                "target_name": c.get("name"),
                "batch_no": None,
            }
            for c in selected
        )
        if next_cursor == 0:
            break
        cursor = next_cursor
    return result


def preview_remaining(campaign: Dict[str, Any], *, run_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Generic preview used by the Live API / remaining endpoint."""
    if campaign.get("campaign_type") == "myGroupLink":
        return preview_remaining_groups(campaign, exclude_core=True, run_id=run_id)
    if campaign.get("campaign_type") == "product_client":
        return preview_remaining_clients(campaign, run_id=run_id)
    return preview_remaining_groups(campaign, run_id=run_id)


# ── messaging ───────────────────────────────────────────────────────────


def build_product_text(product: Dict[str, Any]) -> str:
    parts: List[str] = []
    if product.get("name"):
        parts.append(f"*{product['name']}*")
    if product.get("description"):
        parts.append(str(product["description"]).strip())
    if product.get("link"):
        parts.append(str(product["link"]).strip())
    return "\n".join(parts) or "*New product*"


def build_link_text(group: Dict[str, Any]) -> str:
    name = group.get("name") or "Our community"
    link = group.get("link") or ""
    return f"*{name}*\n{link}".strip()


# ── analytics ───────────────────────────────────────────────────────────


def record_campaign_post(
    campaign_id: int,
    target_type: str,
    target_id: Optional[int],
    target_name: str,
    status: str = "sent",
    product_id: Optional[int] = None,
) -> int:
    """Persist one campaign target result and roll it into today's analytics."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO campaign_posts (campaign_id, target_type, target_id, target_name, status, product_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (campaign_id, target_type, target_id, target_name, status, product_id),
    )
    post_id = int(cur.lastrowid)
    if status == "sent":
        today = datetime.now().strftime("%Y-%m-%d")
        groups_reached = 1 if target_type == "group" else 0
        row = conn.execute("SELECT id FROM analytics WHERE date = ?", (today,)).fetchone()
        if row:
            conn.execute(
                "UPDATE analytics SET posts_sent = posts_sent + 1, "
                "groups_reached = groups_reached + ? WHERE id = ?",
                (groups_reached, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO analytics (date, posts_sent, groups_reached) VALUES (?, 1, ?)",
                (today, groups_reached),
            )
    conn.commit()
    conn.close()
    return post_id


def set_campaign_status(cid: int, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, cid))
    conn.commit()
    conn.close()


def _next_run_still_future(cid: int) -> bool:
    """True when a manual early run must leave the existing slot untouched."""
    from scheduling import now_minute, parse_dt

    conn = get_conn()
    row = conn.execute("SELECT next_run_at FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row or not row["next_run_at"]:
        return False
    scheduled = parse_dt(row["next_run_at"])
    return bool(scheduled and scheduled > now_minute())


# ── runner ──────────────────────────────────────────────────────────────


def _resolve_product(campaign: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if campaign.get("auto_product"):
        product = pick_equitable_random_product(bool(campaign.get("rePost")))
        if product:
            mark_product_pending(product["id"])
            product["status"] = "isPending"
        return product

    pid = campaign.get("product_id")
    if not pid:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return None
    product = dict(row)
    if product["status"] == "isPosted" and not campaign.get("rePost"):
        log(
            "info",
            f"campaign {campaign['id']} skipped: product '{product['name']}' is already posted "
            "(enable Re-post to send it again)",
            "campaign_runner",
        )
        return None
    mark_product_pending(pid)
    return product


def run_campaign(cid: int) -> None:
    """Run a campaign that has already been claimed with try_claim_campaign()."""
    clear_cancel(cid)
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        log("error", f"campaign {cid} not found", "campaign_runner")
        return
    campaign = dict(row)

    reset_products_if_all_posted()
    reset_daily_group_counts()
    refresh_pending_products()

    posts_sent = 0
    cancelled = False
    run_id: Optional[int] = None
    run_status = "completed"
    run_error: Optional[str] = None
    session_limit = max(1, app_settings.get_int("qr_after_logins", 1))
    try:
        run_id = run_state.start_run(campaign)
        run_state.set_run_phase(run_id, status="running", phase="resolving_targets")

        product = None
        if campaign["campaign_type"] in ("product_group", "product_client"):
            product = _resolve_product(campaign)
            if not product:
                log("info", f"campaign {cid} has no product to post", "campaign_runner")
                run_state.record_event(
                    run_id,
                    "info",
                    "run_finished",
                    f"Campaign {cid} has no product to post; run finished",
                    campaign_id=cid,
                )
                return
            run_state.set_run_product(run_id, product)

        session_info = prepare_session_for_run()
        session_limit = int(session_info.get("limit") or session_limit)

        # Headless hides the QR, so a run that needs a fresh pairing opens a
        # visible browser, waits for the scan, closes it, then the run
        # relaunches hidden with the saved session.
        if app_settings.get_bool("headless", False) and (
            session_info.get("cleared") or not _session_dir_has_files()
        ):
            if not pair_headed_for_run(cid):
                raise RuntimeError(
                    "WhatsApp pairing did not complete. A browser window was opened "
                    "for the QR scan but login was not detected (cancelled, closed, or timed out). "
                    "Run the campaign again and scan the QR code."
                )

        bot = get_bot(headless=app_settings.get_bool("headless", False))
        app_settings.set_meta_int(
            SESSION_RUNS_KEY,
            app_settings.get_meta_int(SESSION_RUNS_KEY, 0) + 1,
        )
        bot.cancel_event = _event_for(cid)
        run_state.set_run_phase(run_id, status="running", phase="batch_starting")
        if campaign["campaign_type"] == "product_group":
            posts_sent, complete = _run_paced_batches(
                cid, campaign, lambda: run_product_group(campaign, product, bot, run_id), "group", run_id
            )
            if product and posts_sent and complete:
                mark_product_posted(product["id"])
        elif campaign["campaign_type"] == "product_client":
            posts_sent, complete = _run_paced_batches(
                cid, campaign, lambda: run_product_client(campaign, product, bot, run_id), "client", run_id
            )
            if product and posts_sent and complete:
                mark_product_posted(product["id"])
        elif campaign["campaign_type"] == "myGroupLink":
            posts_sent, _ = _run_paced_batches(
                cid, campaign, lambda: run_my_group_link(campaign, bot, run_id), "group", run_id
            )

        if product and posts_sent == 0:
            clear_pending_if_unused(product["id"])
    except Exception as exc:
        run_error = str(exc)
        run_status = "failed"
        log("error", f"campaign {cid} failed: {exc}", "campaign_runner")
    finally:
        cancelled = is_cancelled(cid)
        if run_error:
            run_status = "failed"
        elif cancelled:
            run_status = "stopped"
        run_state.finish_run(run_id, run_status, run_error)
        conn = get_conn()
        conn.execute(
            "UPDATE campaigns SET posts_sent = posts_sent + ?, last_run_at = datetime('now') WHERE id = ?",
            (posts_sent, cid),
        )
        conn.commit()
        conn.close()

        if cancelled:
            set_campaign_status(cid, "isPosted")
            conn = get_conn()
            conn.execute("UPDATE campaigns SET next_run_at = NULL WHERE id = ?", (cid,))
            conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
            conn.commit()
            conn.close()
            log("info", f"campaign {cid} stopped; posts_sent={posts_sent}", "campaign_runner")
            # Safe here: we are on the runner thread, not a request thread.
            stop_bot()
        elif _next_run_still_future(cid):
            # This was a manual early run; the real scheduled slot is still ahead.
            set_campaign_status(cid, "isScheduledFor")
            log(
                "info",
                f"campaign {cid} manual run finished; posts_sent={posts_sent}; scheduled slot kept",
                "campaign_runner",
            )
        elif campaign.get("repeatPost"):
            upcoming = advance_after_run(cid)
            set_campaign_status(cid, "isScheduledFor" if upcoming else "isPosted")
            log("info", f"campaign {cid} finished; posts_sent={posts_sent}; next={upcoming}", "campaign_runner")
        else:
            conn = get_conn()
            conn.execute("UPDATE campaigns SET next_run_at = NULL WHERE id = ?", (cid,))
            conn.execute("DELETE FROM schedules WHERE campaign_id = ?", (cid,))
            conn.commit()
            conn.close()
            set_campaign_status(cid, "isPosted")
            log("info", f"campaign {cid} finished; posts_sent={posts_sent}", "campaign_runner")
        refresh_pending_products()
        # Reference behaviour: once every product has been posted, start a new
        # cycle immediately instead of waiting for the next run.
        reset_products_if_all_posted()

        # The profile is allowed this many runs between QR scans. Stopping the
        # browser here makes the next run relaunch and (when the limit is
        # reached) show a fresh QR instead of silently reusing a stale session.
        if app_settings.get_meta_int(SESSION_RUNS_KEY, 0) >= session_limit:
            stop_bot()
            log(
                "info",
                "[session] run limit reached; browser stopped so the next run can ask for a QR",
                "poster",
            )


def _run_target_progress(
    run_id: Optional[int],
    campaign: Dict[str, Any],
    target_type: str,
    target_id: int,
    target_name: str,
) -> tuple[Any, Any]:
    """Build the poster ``on_event``/``should_skip`` callbacks for one target."""

    def on_event(message: str) -> None:
        run_state.record_event(
            run_id,
            "info",
            "progress",
            message,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            campaign_id=campaign["id"],
        )

    def should_skip() -> bool:
        return run_state.skip_requested(campaign["id"])

    return on_event, should_skip


def run_product_group(
    campaign: Dict[str, Any],
    product: Dict[str, Any],
    bot: WhatsAppBot,
    run_id: Optional[int] = None,
) -> int:
    groups = pick_group_batch(campaign)
    if not groups:
        log("info", f"campaign {campaign['id']}: no eligible groups (daily limit or disabled)", "campaign_runner")
        run_state.record_event(
            run_id,
            "info",
            "target_deferred",
            f"Campaign {campaign['id']}: no eligible groups (daily limit, disabled or silenced)",
            campaign_id=campaign["id"],
        )
        return 0

    run_state.create_run_targets(
        run_id, campaign["id"], groups, target_type="group",
    )

    text = build_product_text(product)
    sent = 0
    for group in groups:
        if is_cancelled(campaign["id"]):
            break

        # Checkpoint: skip requested before this target even starts.
        if run_state.consume_skip(campaign["id"]):
            run_state.record_event(
                run_id, "info", "target_skipped",
                f"Skipped '{group['name']}' before opening the chat",
                target_type="group", target_id=group["id"], target_name=group["name"],
                campaign_id=campaign["id"],
            )
            run_state.record_target_result(
                run_id, "group", group["id"], "skipped",
                "Skipped by user", target_name=group["name"], campaign_id=campaign["id"],
            )
            continue

        run_state.set_current_target(run_id, "group", group["id"], group["name"], phase="opening_chat")
        if not bot.ensure_connection(f"product_group:{group['name']}"):
            log("error", "WhatsApp connection lost; stopping campaign", "campaign_runner")
            run_state.release_current_target(
                run_id, "group", group["id"], "WhatsApp connection lost before the attempt",
            )
            run_state.record_event(
                run_id, "error", "error",
                f"WhatsApp connection lost before posting to '{group['name']}'; target left pending",
                target_type="group", target_id=group["id"], target_name=group["name"],
                campaign_id=campaign["id"],
            )
            break

        if not can_post_to_group(group, repost=bool(campaign.get("rePost"))):
            run_state.record_target_result(
                run_id, "group", group["id"], "deferred",
                "Daily cap reached, disabled or silenced",
                target_name=group["name"], campaign_id=campaign["id"],
            )
            continue

        on_event, should_skip = _run_target_progress(
            run_id, campaign, "group", group["id"], group["name"],
        )
        run_state.set_run_phase(run_id, phase="posting")
        run_state.record_event(
            run_id, "info", "target_opening",
            f"Posting '{product['name']}' to '{group['name']}'",
            target_type="group", target_id=group["id"], target_name=group["name"],
            campaign_id=campaign["id"],
        )
        log("info", f"posting '{product['name']}' to '{group['name']}'", "campaign_runner")
        ok = post_product(
            bot, group["name"], product, text, "group",
            on_event=on_event, should_skip=should_skip,
        )
        if ok:
            # A skip that arrived after the send completed is discarded: the
            # post is already out, so it counts as sent.
            run_state.clear_skip(campaign["id"])
            mark_group_posted(group["id"])
            record_group_success(group["id"], run_id=run_id, campaign_id=campaign["id"])
            post_id = record_campaign_post(campaign["id"], "group", group["id"], group["name"], "sent", product.get("id"))
            if campaign.get("capture_replies"):
                capture_post_replies(bot, campaign["id"], group["id"], post_id, run_id)
            run_state.record_target_result(
                run_id, "group", group["id"], "sent", "Sent",
                target_name=group["name"], campaign_id=campaign["id"],
            )
            sent += 1
        elif run_state.skip_requested(campaign["id"]):
            run_state.clear_skip(campaign["id"])
            run_state.record_target_result(
                run_id, "group", group["id"], "skipped", "Skipped by user",
                target_name=group["name"], campaign_id=campaign["id"],
            )
        else:
            outcome = record_group_failure(
                group["id"], "post failed",
                run_id=run_id, campaign_id=campaign["id"], target_name=group["name"],
            )
            if outcome != "skipped":
                record_campaign_post(campaign["id"], "group", group["id"], group["name"], "failed")
                run_state.record_target_result(
                    run_id, "group", group["id"], "failed", "Post failed or could not be confirmed",
                    target_name=group["name"], campaign_id=campaign["id"],
                )
    return sent


def run_product_client(
    campaign: Dict[str, Any],
    product: Dict[str, Any],
    bot: WhatsAppBot,
    run_id: Optional[int] = None,
) -> int:
    clients = pick_client_batch(campaign)
    if not clients:
        log("info", f"campaign {campaign['id']}: no client selected", "campaign_runner")
        run_state.record_event(
            run_id, "info", "target_deferred",
            f"Campaign {campaign['id']}: no client selected",
            campaign_id=campaign["id"],
        )
        return 0

    run_state.create_run_targets(run_id, campaign["id"], clients, target_type="client")

    text = build_product_text(product)
    sent = 0
    for client in clients:
        if is_cancelled(campaign["id"]):
            break

        if run_state.consume_skip(campaign["id"]):
            run_state.record_event(
                run_id, "info", "target_skipped",
                f"Skipped client '{client['name']}' before opening the chat",
                target_type="client", target_id=client["id"], target_name=client["name"],
                campaign_id=campaign["id"],
            )
            run_state.record_target_result(
                run_id, "client", client["id"], "skipped", "Skipped by user",
                target_name=client["name"], campaign_id=campaign["id"],
            )
            continue

        run_state.set_current_target(run_id, "client", client["id"], client["name"], phase="opening_chat")
        if not bot.ensure_connection(f"product_client:{client['name']}"):
            run_state.release_current_target(
                run_id, "client", client["id"], "WhatsApp connection lost before the attempt",
            )
            break

        on_event, should_skip = _run_target_progress(
            run_id, campaign, "client", client["id"], client["name"],
        )
        run_state.set_run_phase(run_id, phase="posting")
        run_state.record_event(
            run_id, "info", "target_opening",
            f"Posting '{product['name']}' to client '{client['name']}'",
            target_type="client", target_id=client["id"], target_name=client["name"],
            campaign_id=campaign["id"],
        )
        log("info", f"posting '{product['name']}' to client '{client['name']}'", "campaign_runner")
        ok = post_product(
            bot, client["number"], product, text, "client",
            on_event=on_event, should_skip=should_skip,
        )
        if ok:
            run_state.clear_skip(campaign["id"])
            record_campaign_post(campaign["id"], "client", client["id"], client["name"], "sent")
            run_state.record_target_result(
                run_id, "client", client["id"], "sent", "Sent",
                target_name=client["name"], campaign_id=campaign["id"],
            )
            sent += 1
        elif run_state.skip_requested(campaign["id"]):
            run_state.clear_skip(campaign["id"])
            run_state.record_target_result(
                run_id, "client", client["id"], "skipped", "Skipped by user",
                target_name=client["name"], campaign_id=campaign["id"],
            )
        else:
            record_campaign_post(campaign["id"], "client", client["id"], client["name"], "failed")
            run_state.record_target_result(
                run_id, "client", client["id"], "failed", "Post failed or could not be confirmed",
                target_name=client["name"], campaign_id=campaign["id"],
            )
    return sent


def _next_my_group_link(campaign: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM groups WHERE is_my_group = 1 AND is_active = 1 "
        "AND COALESCE(is_silenced, 0) = 0 "
        "AND link IS NOT NULL AND TRIM(link) != '' ORDER BY is_core DESC, id"
    ).fetchall()]
    conn.close()
    if not rows:
        return None
    key = f"campaign:{campaign['id']}:link_cursor"
    cursor = _meta_get(key)
    upcoming = [r for r in rows if r["id"] > cursor]
    chosen = upcoming[0] if upcoming else rows[0]
    _meta_set(key, chosen["id"])
    return chosen


def run_my_group_link(
    campaign: Dict[str, Any],
    bot: WhatsAppBot,
    run_id: Optional[int] = None,
) -> int:
    source = _next_my_group_link(campaign)
    if not source:
        log("info", "no 'my group' has a link yet; add links under Groups", "campaign_runner")
        run_state.record_event(
            run_id, "info", "target_deferred",
            "No 'my group' with a link is available",
            campaign_id=campaign["id"],
        )
        return 0

    # The promoted group is the current "product"/source for a link campaign.
    run_state.set_run_product(run_id, source)

    groups = pick_group_batch(campaign, exclude_core=True, exclude_name=source["name"])
    if not groups:
        log("info", f"campaign {campaign['id']}: no eligible non-core groups", "campaign_runner")
        run_state.record_event(
            run_id, "info", "target_deferred",
            f"Campaign {campaign['id']}: no eligible non-core groups",
            campaign_id=campaign["id"],
        )
        return 0

    run_state.create_run_targets(
        run_id, campaign["id"], groups, target_type="group", source_name=source["name"],
    )

    text = build_link_text(source)
    sent = 0
    for group in groups:
        if is_cancelled(campaign["id"]):
            break

        if run_state.consume_skip(campaign["id"]):
            run_state.record_event(
                run_id, "info", "target_skipped",
                f"Skipped '{group['name']}' before opening the chat",
                target_type="group", target_id=group["id"], target_name=group["name"],
                campaign_id=campaign["id"],
            )
            run_state.record_target_result(
                run_id, "group", group["id"], "skipped", "Skipped by user",
                target_name=group["name"], campaign_id=campaign["id"],
            )
            continue

        run_state.set_current_target(
            run_id, "group", group["id"], group["name"], phase="opening_chat",
        )
        if not bot.ensure_connection(f"link_campaign:{group['name']}"):
            run_state.release_current_target(
                run_id, "group", group["id"], "WhatsApp connection lost before the attempt",
            )
            break

        if not can_post_to_group(group, repost=bool(campaign.get("rePost"))):
            run_state.record_target_result(
                run_id, "group", group["id"], "deferred",
                "Daily cap reached, disabled or silenced",
                target_name=group["name"], campaign_id=campaign["id"],
            )
            continue

        on_event, should_skip = _run_target_progress(
            run_id, campaign, "group", group["id"], group["name"],
        )
        run_state.set_run_phase(run_id, phase="posting")
        run_state.record_event(
            run_id, "info", "target_opening",
            f"Promoting link '{source['name']}' to '{group['name']}'",
            target_type="group", target_id=group["id"], target_name=group["name"],
            campaign_id=campaign["id"],
        )
        log("info", f"marketing link '{source['name']}' to '{group['name']}'", "campaign_runner")
        ok = post_text(bot, group["name"], text, "group", on_event=on_event, should_skip=should_skip)
        if ok:
            run_state.clear_skip(campaign["id"])
            mark_group_posted(group["id"])
            record_group_success(group["id"], run_id=run_id, campaign_id=campaign["id"])
            post_id = record_campaign_post(campaign["id"], "group", group["id"], group["name"], "sent")
            if campaign.get("capture_replies"):
                capture_post_replies(bot, campaign["id"], group["id"], post_id, run_id)
            run_state.record_target_result(
                run_id, "group", group["id"], "sent", "Sent",
                target_name=group["name"], campaign_id=campaign["id"],
            )
            sent += 1
        elif run_state.skip_requested(campaign["id"]):
            run_state.clear_skip(campaign["id"])
            run_state.record_target_result(
                run_id, "group", group["id"], "skipped", "Skipped by user",
                target_name=group["name"], campaign_id=campaign["id"],
            )
        else:
            outcome = record_group_failure(
                group["id"], "link post failed",
                run_id=run_id, campaign_id=campaign["id"], target_name=group["name"],
            )
            if outcome != "skipped":
                record_campaign_post(campaign["id"], "group", group["id"], group["name"], "failed")
                run_state.record_target_result(
                    run_id, "group", group["id"], "failed", "Post failed or could not be confirmed",
                    target_name=group["name"], campaign_id=campaign["id"],
                )
    return sent


# ── scheduler ───────────────────────────────────────────────────────────


def due_campaigns() -> List[Dict[str, Any]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM campaigns "
        "WHERE next_run_at IS NOT NULL AND next_run_at <= ? "
        "AND status IN ('isScheduledFor', 'isBusy') ORDER BY next_run_at",
        (now,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run_due_campaigns() -> None:
    for campaign in due_campaigns():
        cid = campaign["id"]
        if try_claim_campaign(cid):
            run_campaign(cid)
        else:
            when = defer_campaign(cid)
            log(
                "info",
                f"campaign {cid} is busy; moved to next free slot {when}",
                "scheduler",
            )


def sync_all_campaigns() -> None:
    """Generate schedules for campaigns that are waiting to run."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM campaigns WHERE status IN ('isScheduledFor', 'isBusy')"
    ).fetchall()
    conn.close()
    for row in rows:
        sync_campaign_schedule(row["id"])


# Backwards-compatible aliases used by main.py / __init__.
def due_schedules() -> List[Dict[str, Any]]:
    return due_campaigns()


def run_due_schedules() -> None:
    run_due_campaigns()


def check_schedule_conflicts(start_time: str, end_time: str, exclude_schedule_id: Optional[int] = None) -> bool:
    conn = get_conn()
    sql = "SELECT COUNT(*) AS c FROM schedules WHERE status = 'active' AND start_time < ? AND end_time > ?"
    params: List[Any] = [end_time, start_time]
    if exclude_schedule_id is not None:
        sql += " AND id != ?"
        params.append(exclude_schedule_id)
    row = conn.execute(sql, tuple(params)).fetchone()
    conn.close()
    return (row["c"] if row else 0) == 0
