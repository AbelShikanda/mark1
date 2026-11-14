"""WhatsApp Web posting primitives.

All methods are synchronous and receive an already-connected ``WhatsAppBot``.
Every target attempt creates one :class:`~bot.diagnostics.Trace`, which records
the search, group selection, composer, typing, link-preview and send steps to
the per-target trace file, the Live feed and the ``logs`` table.

The search/open flow follows the reference poster: click the real chat-list
search container, fill the whole group name once, match both the extracted
chat title and the whole row text, then treat the message composer as the
authoritative "chat opened" signal. Connection checks deliberately avoid a
reload after the search is filled, because that wipes the results and makes
every later group look missing.
"""

from __future__ import annotations

import hashlib
import random
import re
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import (
    AFTER_TYPING_WAIT,
    FIND_COMPOSE_WAIT,
    LINK_PREVIEW_DELAY,
    OPEN_WAIT,
    RETRY_DELAY,
    SEARCH_WAIT,
    SEND_CONFIRM_WAIT,
    TYPING_DELAY_MAX,
    TYPING_DELAY_MIN,
    UPLOAD_DIR,
)
from db_logic import log
from . import run_state
from . import settings as app_settings
from .diagnostics import Trace, describe_results_line
from .login_manager import WhatsAppBot

# Clicking the chat-list search container first opens the real search field in
# current WhatsApp Web builds where the field itself is not rendered until the
# container is focused.
SEARCH_CONTAINERS = [
    '#side div[data-testid="chat-list-search"]',
    '#side button[aria-label="Search"]',
    '#side div[aria-label="Search"]',
    '#side div[data-tab="1"]',
]

# Scoped to the left pane so the message composer can never be mistaken for
# the search box. Direct inputs are tried before generic textboxes.
SEARCH_INPUTS = [
    '#side input[type="text"]',
    '#side div[data-testid="chat-list-search"] input',
    '#side div[role="textbox"]',
    '#side div[contenteditable="true"][data-tab="3"]',
    '#side div[aria-label="Search input textbox"]',
    '#side div[title="Search input textbox"]',
    'div[data-testid="chat-list-search"] input',
    'div[aria-label="Search input textbox"]',
    'div[title="Search input textbox"]',
    'div[contenteditable="true"][data-tab="3"]',
    'input[type="text"]',
]

CHAT_ROWS = [
    '#pane-side div[role="row"]',
    '#pane-side div[role="listitem"]',
    'div[role="row"]',
    'div[role="listitem"]',
    'div[data-testid="cell-frame-container"]',
]

CHAT_TITLE_SELECTORS = [
    'span[data-testid="chat-name"]',
    'div[data-testid="cell-frame-title"] span',
    'span[data-testid="cell-frame-title"]',
    'div[data-testid="cell-frame-title"]',
    'span[title]',
    'div[title]',
]

HEADER_TITLE_SELECTORS = [
    'span[data-testid="conversation-info-header-chat-title"]',
    '[data-testid="conversation-info-header-chat-title"]',
    'div[data-testid="conversation-info-header-chat-title-name"]',
    '#main header span[title]',
    '#main header span[dir="auto"]',
    '#main header h1',
]

# A stale linked-device session (or an account that is no longer a member) can
# still open the conversation, but WhatsApp replaces the composer with a
# read-only notice. Report that clearly instead of retrying as a click failure.
RESTRICTED_TEXTS = [
    "can't send messages to this group",
    "you're no longer a member",
    "you are no longer a member",
    "only admins can send",
    "messages to this group are disabled",
    "this group is read-only",
    "you cannot send messages",
]

# Prefer the conversation composer inside #main. The reference poster used the
# same selector family; extra variants cover current WhatsApp builds.
COMPOSE_INPUTS = [
    '#main footer div[contenteditable="true"]',
    '#main > footer p',
    '#main footer p',
    '#main div[contenteditable="true"][role="textbox"]',
    '#main div[aria-label="Type a message"]',
    '#main div[data-testid="conversation-compose-box-input"]',
    '#main div[data-testid="conversation-compose-box"]',
    '#main p[contenteditable="true"]',
    '#main div[contenteditable="true"]',
    'footer div[contenteditable="true"]',
    'div[aria-label="Type a message"]',
    'div[data-testid="conversation-compose-box"]',
    'div[role="textbox"]',
    'div[data-testid="conversation-compose-box-input"]',
    'div[contenteditable="true"][role="textbox"]',
    'p[contenteditable="true"]',
]

# After attaching an image WhatsApp shows a dedicated caption field instead of
# the normal footer composer, so image posts must look here first.
CAPTION_INPUTS = [
    '#main div[data-testid="media-caption-input"] div[contenteditable="true"]',
    '#main div[data-testid="media-caption-input"]',
    '#main div[aria-label="Add a caption"]',
    'div[data-testid="media-caption-input"] div[contenteditable="true"]',
    'div[data-testid="media-caption-input"]',
    'div[aria-label="Add a caption"]',
]

SEND_BUTTONS = [
    'button[aria-label="Send"]',
    'span[data-icon="send"]',
    'button[data-testid="compose-btn-send"]',
]

ATTACH_BUTTONS = [
    'button[aria-label="Attach"]',
    'div[title="Attach"]',
    'span[data-icon="attach-menu-plus"]',
    'span[data-icon="plus"]',
    'span[data-icon="clip"]',
]

LINK_PREVIEW_SELECTORS = [
    'div[data-testid="link-preview"]',
    'div[data-testid="link"]',
    'div[aria-label="Link preview"]',
    'div[data-testid="message-link"]',
    'div[data-testid="image-container"]',
]

EventCallback = Optional[Callable[[str], None]]
SkipCheck = Optional[Callable[[], bool]]


# ── small helpers ───────────────────────────────────────────────────────


def _visible(page, selector: str):
    try:
        element = page.query_selector(selector)
        return element if element and element.is_visible() else None
    except Exception:
        return None


def _first_visible(page, selectors) -> Tuple[Any, Optional[str]]:
    for selector in selectors:
        element = _visible(page, selector)
        if element:
            return element, selector
    return None, None


def _emit(on_event: EventCallback, message: str) -> None:
    if on_event is None:
        return
    try:
        on_event(message)
    except Exception:
        pass


def _skip_requested(should_skip: SkipCheck) -> bool:
    if should_skip is None:
        return False
    try:
        return bool(should_skip())
    except Exception:
        return False


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _preview(text: str, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _make_trace(
    on_event: EventCallback,
    target: str,
    run_id: Optional[int] = None,
    attempt: int = 1,
    attempts: int = 3,
) -> Trace:
    if run_id is None:
        try:
            run_id = run_state.active_run_id()
        except Exception:
            run_id = None
    return Trace(on_event, target, run_id=run_id, attempt=attempt, attempts=attempts)


# ── search box ──────────────────────────────────────────────────────────


def _find_search_input(page) -> Tuple[Any, Optional[str]]:
    return _first_visible(page, SEARCH_INPUTS)


def _click_first(page, selectors) -> Optional[str]:
    for selector in selectors:
        element = _visible(page, selector)
        if not element:
            continue
        try:
            element.click(timeout=3000)
            return selector
        except Exception:
            continue
    return None


def _enter_search(page, target: str, trace: Optional[Trace] = None) -> bool:
    """Open the chat-list search, clear it and fill the whole target once."""
    search, selector = _find_search_input(page)

    if not search:
        clicked = _click_first(page, SEARCH_CONTAINERS)
        if clicked and trace:
            trace.step("search", "container clicked", f"selector={clicked}")
        if clicked:
            time.sleep(0.6)
            search, selector = _find_search_input(page)

    if not search:
        # One controlled retry. Deliberately NOT Control+f + blind typing: if
        # the pane is not focused that writes into the message composer.
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.3)
        retry_focus = _click_first(
            page,
            [
                '#side div[data-tab="1"]',
                '#side div[data-testid="chat-list-search"]',
                '#side button[aria-label="Search"]',
            ],
        )
        if retry_focus:
            time.sleep(0.5)
            clicked = _click_first(page, SEARCH_CONTAINERS)
            if clicked:
                time.sleep(0.6)
        search, selector = _find_search_input(page)

    if not search:
        if trace:
            trace.fail("search", "search", "search box not found after retry")
            trace.capture(page, "search_box")
        log("warning", f"search box not found for '{target}'", "poster")
        return False

    if trace:
        trace.step("search", "box found", f"selector={selector}")

    try:
        search.click(timeout=3000)
        if trace:
            trace.step("search", "clicked")
        time.sleep(0.2)

        try:
            search.fill("")
        except Exception:
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
        if trace:
            trace.step("search", "cleared")

        method = "fill"
        try:
            search.fill(target)
        except Exception:
            method = "type"
            search.type(target, delay=45)
        if trace:
            trace.step("search", "filled", f'text="{_preview(target)}" | method={method}')
    except Exception as exc:
        if trace:
            trace.fail("search", "search", f"{type(exc).__name__}: {exc}")
            trace.capture(page, "search_fill")
        log("warning", f"search failed for '{target}': {exc}", "poster")
        return False

    wait = app_settings.get_float("search_wait", SEARCH_WAIT) + random.uniform(0, 2)
    if trace:
        trace.step("search", "waiting", f"{wait:.1f}s")
    time.sleep(wait)
    return True


def _reset_chat_list(page, trace: Optional[Trace] = None) -> None:
    """Close overlays and clear the previous search before a target attempt."""
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    time.sleep(0.2)

    search, _ = _find_search_input(page)
    if search:
        try:
            search.fill("")
        except Exception:
            try:
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
            except Exception:
                pass
        if trace:
            trace.step("search", "cleared", "before target")

    if not _rows_visible(page):
        clicked = _click_first(
            page,
            ['#side div[data-tab="1"]', '#side div[data-testid="chat-list-search"]'],
        )
        if clicked and trace:
            trace.step("search", "chats tab clicked", f"selector={clicked}")
        time.sleep(0.3)


# ── result matching ─────────────────────────────────────────────────────


def _row_title(row) -> str:
    """Read the chat title of a result row, ignoring its preview text."""
    for selector in CHAT_TITLE_SELECTORS:
        try:
            element = row.query_selector(selector)
        except Exception:
            element = None
        if not element:
            continue
        try:
            title = element.get_attribute("title") or element.inner_text()
        except Exception:
            continue
        title = (title or "").strip()
        if title:
            return title
    return _row_text(row)


def _row_text(row) -> str:
    try:
        return (row.inner_text() or "").strip()
    except Exception:
        return ""


def _title_score(wanted: str, title: str) -> int:
    normalised = _normalise(title)
    if not normalised or not wanted:
        return 0
    if normalised == wanted:
        return 3
    if normalised.startswith(wanted):
        return 2
    if wanted in normalised:
        return 1
    return 0


def _candidate_score(wanted: str, title: str, row_text: str) -> float:
    """Score a row on both its extracted title and its full text.

    A timestamp or preview text used as the "title" must not hide a row whose
    full text contains the target; that row gets the lowest (row-text) score.
    Ordering: exact title (3) > starts-with (2) > contains (1) > row text (0.5).
    """
    score = _title_score(wanted, title)
    if score == 0 and wanted and wanted in _normalise(row_text):
        score = 0.5
    return score


def _candidate_fp(candidate: Dict[str, Any]) -> Tuple[str, str]:
    return (_normalise(candidate.get("title", "")), _normalise(candidate.get("row_text", "")))


def _rows_visible(page) -> bool:
    for selector in CHAT_ROWS:
        try:
            for row in page.query_selector_all(selector):
                try:
                    if row.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _first_visible_row(page):
    for selector in CHAT_ROWS:
        try:
            rows = page.query_selector_all(selector)
        except Exception:
            rows = []
        for row in rows:
            try:
                if row.is_visible():
                    return row
            except Exception:
                continue
    return None


def _find_candidates(page, target: str) -> List[Dict[str, Any]]:
    """Collect every visible row that matches on title or whole-row text."""
    wanted = _normalise(target)
    if not wanted:
        return []
    seen: set = set()
    candidates: List[Dict[str, Any]] = []
    for selector in CHAT_ROWS:
        try:
            rows = page.query_selector_all(selector)
        except Exception:
            rows = []
        for row in rows:
            try:
                if not row.is_visible():
                    continue
            except Exception:
                continue
            row_text = _row_text(row)
            title = _row_title(row)
            score = _candidate_score(wanted, title, row_text)
            if score <= 0:
                continue
            candidate = {
                "row": row,
                "title": title or row_text,
                "score": score,
                "row_text": row_text,
            }
            fingerprint = _candidate_fp(candidate)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            candidates.append(candidate)
    # exact title (3) > starts-with (2) > contains / row text (1)
    candidates.sort(key=lambda item: -item["score"])
    return candidates


# ── opening a candidate ─────────────────────────────────────────────────


def _click_title(row) -> bool:
    for selector in CHAT_TITLE_SELECTORS:
        try:
            element = row.query_selector(selector)
        except Exception:
            element = None
        if not element:
            continue
        try:
            element.click(timeout=3000)
            return True
        except Exception:
            continue
    return False


def _click_row(page, row) -> Optional[str]:
    try:
        row.click(timeout=3000)
        return "row"
    except Exception:
        pass
    try:
        row.click(force=True, timeout=3000)
        return "force"
    except Exception:
        pass
    try:
        box = row.bounding_box()
        if box and box.get("width") and box.get("height"):
            page.mouse.click(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
            )
            return "mouse"
    except Exception:
        pass
    return None


def _wait_for_compose(page, timeout: float = 8.0) -> Tuple[Any, Optional[str]]:
    """Wait until the message composer for the opened chat is visible."""
    interval = max(0.1, app_settings.get_float("find_compose_wait", FIND_COMPOSE_WAIT))
    deadline = time.time() + timeout
    while time.time() < deadline:
        compose, selector = _first_visible(page, COMPOSE_INPUTS)
        if compose:
            return compose, selector
        time.sleep(interval)
    return None, None


def _opened_chat_title(page) -> str:
    """Read the title from the conversation header of the opened chat."""
    for selector in HEADER_TITLE_SELECTORS:
        try:
            element = page.query_selector(selector)
        except Exception:
            element = None
        if not element:
            continue
        try:
            title = element.get_attribute("title") or element.inner_text()
        except Exception:
            continue
        title = (title or "").strip()
        if title:
            return title
    return ""


def _read_only_reason(page) -> str:
    """Return the read-only footer text when WhatsApp blocks sending here."""
    text = ""
    try:
        block = page.query_selector('#main [data-testid="block-message"]')
        if block:
            text = block.inner_text() or ""
    except Exception:
        text = ""
    if not text:
        try:
            footer = page.query_selector('#main footer[data-testid="compose-box"]')
            if footer is None:
                footer = page.query_selector("#main footer")
            if footer:
                text = footer.inner_text() or ""
        except Exception:
            text = ""
    normalised = _normalise(text).replace("\u2019", "'").replace("\u2018", "'")
    if not normalised:
        return ""
    for marker in RESTRICTED_TEXTS:
        if marker in normalised:
            return re.sub(r"\s+", " ", text).strip()
    return ""


def _try_candidate(
    page,
    target: str,
    candidate: Dict[str, Any],
    trace: Optional[Trace],
) -> Tuple[Any, str, str]:
    """Try the title element and then the row itself.

    Returns ``(composer, reason, detail)`` where reason is ``ok``,
    ``read_only`` or ``composer``.
    """
    row = candidate["row"]
    title = candidate.get("title") or ""
    score = candidate.get("score", 0)
    wanted = _normalise(target)

    for method in ("title", "row"):
        if trace:
            trace.step(
                "group",
                "clicking",
                f'candidate="{_preview(title, 60)}" | score={score} | method={method}',
            )
        if method == "title":
            clicked = "title" if _click_title(row) else None
        else:
            clicked = _click_row(page, row)

        if not clicked:
            if trace:
                trace.step("group", "click failed", f"method={method}")
            continue

        if trace:
            detail = "" if clicked == method else f"method={clicked}"
            trace.step("group", "click ok", detail)

        # Give WhatsApp a moment to swap the right pane before polling for the
        # composer (same idea as the reference poster's OPEN_WAIT).
        time.sleep(app_settings.get_float("open_wait", OPEN_WAIT))

        # Read-only groups render a block notice instead of a composer.
        restricted = _read_only_reason(page)
        if restricted:
            if trace:
                trace.step(
                    "group",
                    "chat opened but sending is blocked",
                    f'reason="{_preview(restricted, 160)}"',
                )
            return None, "read_only", restricted

        timeout = 8.0 if method == "title" else 6.0
        compose, compose_selector = _wait_for_compose(page, timeout=timeout)

        header = _opened_chat_title(page)
        if trace:
            if header:
                match = "yes" if _title_score(wanted, header) > 0 else "no"
                trace.step(
                    "group",
                    "header",
                    f'title="{_preview(header, 60)}" | match={match}',
                )
            else:
                trace.step("group", "header", 'title="" | match=unknown')

        if compose:
            if trace:
                trace.step("group", "GROUP SELECTED SUCCESSFULLY")
                trace.step(
                    "composer",
                    "appeared",
                    f"selector={compose_selector} | elapsed={trace.elapsed():.1f}s",
                )
            return compose, "ok", ""

        # The conversation opened, but WhatsApp replaced the composer with a
        # read-only notice (stale linked-device session / no longer a member).
        # Retrying the click cannot help, so report it immediately.
        restricted = _read_only_reason(page)
        if restricted:
            if trace:
                trace.step(
                    "group",
                    "chat opened but sending is blocked",
                    f'reason="{_preview(restricted, 160)}"',
                )
            return None, "read_only", restricted

        if trace:
            trace.step("group", "click did not open composer", f"method={clicked}")

    if trace:
        trace.step(
            "group",
            "candidate failed",
            f'candidate="{_preview(title, 60)}" | reason=no compose box',
        )
    return None, "composer", ""


def _open_candidates(page, target: str, trace: Optional[Trace], looks_like_number: bool):
    """Try every matching candidate until a composer appears.

    Returns ``(composer, reason, detail)`` where reason is ``ok``,
    ``no_search_result``, ``search_box``, ``read_only`` or ``composer``.
    """
    tried: set = set()
    guard = 0
    while guard < 25:
        guard += 1
        if not _rows_visible(page):
            if not _enter_search(page, target, trace):
                return None, "search_box", ""

        candidates = _find_candidates(page, target)
        if not candidates and looks_like_number:
            row = _first_visible_row(page)
            if row:
                row_text = _row_text(row)
                candidates = [
                    {
                        "row": row,
                        "title": _row_title(row) or row_text,
                        "score": 0,
                        "row_text": row_text,
                    }
                ]

        if not candidates:
            if trace:
                trace.step("results", "candidates", "[]")
            return None, "no_search_result", ""

        if trace:
            preview = ", ".join(
                f'"{_preview(item["title"], 50)}" score={item["score"]}'
                for item in candidates[:10]
            )
            trace.step("results", "candidates", f"[{preview}]")

        fresh = [item for item in candidates if _candidate_fp(item) not in tried]
        if not fresh:
            return None, "composer", ""

        candidate = fresh[0]
        tried.add(_candidate_fp(candidate))

        compose, reason, detail = _try_candidate(page, target, candidate, trace)
        if compose:
            return compose, "ok", ""
        if reason == "read_only":
            return None, "read_only", detail

        # A contact/info panel may have opened instead of a conversation. Close
        # it and restore the search results before trying the next candidate.
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.3)
        if not _rows_visible(page):
            if not _enter_search(page, target, trace):
                return None, "search_box", ""

    return None, "composer", ""


def _open_chat_once(bot: WhatsAppBot, target: str, context: str, trace: Optional[Trace] = None) -> bool:
    """One search-and-open attempt (the caller supplies retries)."""
    page = bot.page
    target = (target or "").strip()
    if not target:
        return False
    if bot.cancelled():
        return False

    # Reset overlays/search from the previous target (or the previous attempt).
    _reset_chat_list(page, trace)

    # Use the destructive recovery only *before* the search is filled.
    if not bot.ensure_connection(f"open_chat:search:{context}"):
        if trace:
            trace.fail("session", "session", f"not connected at {context}")
        return False
    if trace:
        trace.step("session", "connected", f"url={getattr(page, 'url', '')}")

    if not _enter_search(page, target, trace):
        return False

    if bot.cancelled():
        return False

    # After the search, never reload: only a definite QR / phone-not-connected
    # marker aborts. An "unknown" state is treated as connected.
    if bot.is_definitely_disconnected():
        if trace:
            trace.fail("session", "session", "disconnected after search")
            trace.capture(page, "disconnected")
        log("warning", f"WhatsApp disconnected while searching '{target}'", "poster")
        return False

    if trace:
        trace.step("results", "rows", describe_results_line(page))

    looks_like_number = bool(re.fullmatch(r"[+\d\s\-()]+", target))
    compose, reason, detail = _open_candidates(page, target, trace, looks_like_number)
    if compose:
        return True

    if reason == "no_search_result":
        if trace:
            trace.fail("group", "search", f"no search result matched '{target}'")
            trace.capture(page, "search_results")
        log("warning", f"no search result matched '{target}'", "poster")
    elif reason == "read_only":
        if trace:
            trace.stop_retries = True
            trace.fail(
                "group",
                "read_only",
                f"chat opened but sending is blocked: {detail}",
            )
            trace.capture(page, "read_only")
        log(
            "warning",
            f"chat '{target}' opened but sending is blocked: {detail}",
            "poster",
        )
    elif reason == "composer":
        if trace:
            trace.fail("group", "composer", f"no compose box for '{target}'")
            trace.capture(page, "composer")
        log("warning", f"chat '{target}' did not open (no compose box)", "poster")
    # reason == "search_box" already logged and captured by _enter_search.
    return False


def open_chat(
    bot: WhatsAppBot,
    target: str,
    context: str = "chat",
    attempts: int = 3,
    trace: Optional[Trace] = None,
) -> bool:
    """Search for a group/contact and open its conversation, retrying like the
    reference poster did (three attempts before recording a group failure)."""
    if bot.cancelled():
        return False
    for attempt in range(1, attempts + 1):
        if bot.cancelled():
            return False
        if _open_chat_once(bot, target, context, trace):
            return True
        if trace is not None and trace.stop_retries:
            log(
                "warning",
                f"not retrying '{target}': the chat opened but sending is blocked",
                "poster",
            )
            return False
        if attempt < attempts:
            delay = app_settings.get_float("retry_delay", RETRY_DELAY) + attempt
            if trace:
                trace.retry(attempt + 1, delay)
            log(
                "warning",
                f"could not open '{target}' (attempt {attempt}/{attempts}); retrying in {delay:.1f}s",
                "poster",
            )
            try:
                bot.page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(delay)
    log("warning", f"'{target}' could not be opened after {attempts} attempts", "poster")
    return False


# ── typing / sending ────────────────────────────────────────────────────


def _type_text(
    bot: WhatsAppBot,
    text: str,
    prefer_caption: bool = False,
    trace: Optional[Trace] = None,
) -> bool:
    page = bot.page
    selectors = CAPTION_INPUTS + COMPOSE_INPUTS if prefer_caption else COMPOSE_INPUTS
    compose, selector = _first_visible(page, selectors)
    if not compose:
        if trace:
            trace.fail("composer", "composer", "no compose box")
            trace.capture(bot.page, "composer")
        log("warning", "typing failed: no compose box", "poster")
        return False

    try:
        enabled = True
        try:
            enabled = compose.is_enabled()
        except Exception:
            enabled = True
        if trace:
            trace.step(
                "composer",
                "found",
                f"selector={selector} | visible=yes | enabled={'yes' if enabled else 'no'}",
            )

        compose.click()
        if trace:
            trace.step("composer", "clicked")
        time.sleep(0.3)

        try:
            compose.fill("")
        except Exception:
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
        if trace:
            trace.step("composer", "cleared")

        lines = text.split("\n")
        if trace:
            trace.step("typing", "started", f"lines={len(lines)} | chars={len(text)}")
            trace.file_only("[typing] full text:\n" + text)

        typing_low, typing_high = sorted(
            (
                app_settings.get_int("typing_delay_min", TYPING_DELAY_MIN),
                app_settings.get_int("typing_delay_max", TYPING_DELAY_MAX),
            )
        )
        for index, line in enumerate(lines):
            if bot.cancelled():
                return False
            if not line:
                page.keyboard.press("Shift+Enter")
                continue
            compose.type(line, delay=random.randint(typing_low, typing_high))
            if index < len(lines) - 1:
                page.keyboard.press("Shift+Enter")
            if random.random() < 0.04:
                time.sleep(random.uniform(0.2, 0.5))
        time.sleep(0.8)

        if trace:
            trace.step("typing", "finished")

        typed = ""
        try:
            typed = compose.inner_text() or ""
        except Exception:
            typed = ""
        matches = _normalise(typed) == _normalise(text) or _normalise(text) in _normalise(typed)
        if trace:
            trace.step(
                "typing",
                "verified",
                f'composer_text="{_preview(typed, 80)}" | matches={"yes" if matches else "no"}',
            )
        return True
    except Exception as exc:
        if trace:
            trace.fail("typing", "typing", f"{type(exc).__name__}: {exc}")
            trace.capture(bot.page, "typing")
        log("warning", f"typing failed: {exc}", "poster")
        return False


def _has_url(text: str) -> bool:
    return bool(re.search(r"(?:https?://|www\.)\S+", text or "", re.IGNORECASE))


def _wait_for_link_preview(bot: WhatsAppBot, text: str, trace: Optional[Trace] = None) -> None:
    """Wait until WhatsApp finishes generating a link preview."""
    if not _has_url(text):
        if trace:
            trace.step("preview", "skipped", "no URL in message")
        return

    page = bot.page
    limit = app_settings.get_int("link_preview_delay", LINK_PREVIEW_DELAY)
    if trace:
        trace.step("preview", "url detected", f"waiting up to {limit}s")

    found_selector: Optional[str] = None
    deadline = time.time() + max(1, limit)
    while time.time() < deadline:
        if bot.cancelled():
            return
        # WhatsApp replaces the raw URL in the draft with a preview card; if
        # the visible draft no longer contains a URL, the preview is ready.
        try:
            draft = page.evaluate(
                """() => {
                    const el = document.querySelector('#main div[data-testid="message-text"]');
                    return el ? el.textContent : '';
                }"""
            )
        except Exception:
            draft = ""
        if draft and not _has_url(draft):
            found_selector = "draft:url-replaced"
            break
        for selector in LINK_PREVIEW_SELECTORS:
            if _visible(page, selector):
                found_selector = selector
                break
        if found_selector:
            break
        time.sleep(1)

    if found_selector:
        if trace:
            trace.step("preview", "found", f"selector={found_selector}")
    else:
        if trace:
            trace.step("preview", "not found", f"waited {limit}s; sending anyway")

    if trace:
        trace.step("preview", "grace wait", "0.6s")
    time.sleep(0.6)

    if not found_selector:
        # No preview appeared within the limit; wait a little longer rather
        # than dropping the card silently.
        time.sleep(2)


def _press_send(bot: WhatsAppBot, trace: Optional[Trace] = None) -> bool:
    page = bot.page
    time.sleep(
        app_settings.get_float("after_typing_wait", AFTER_TYPING_WAIT) + random.uniform(0, 1)
    )

    if trace:
        trace.step("send", "pressing Enter")
    try:
        page.keyboard.press("Enter")
    except Exception as exc:
        if trace:
            trace.fail("send", "send", f"{type(exc).__name__}: {exc}")
        log("warning", f"could not press Enter to send: {exc}", "poster")
        return False

    time.sleep(
        app_settings.get_float("send_confirm_wait", SEND_CONFIRM_WAIT) + random.uniform(0, 2)
    )

    # If the compose box still contains the text, Enter did not send it; use the
    # send button instead.
    compose, _ = _first_visible(page, COMPOSE_INPUTS)
    remaining = ""
    if compose:
        try:
            remaining = (compose.inner_text() or "").strip()
        except Exception:
            remaining = ""
    if trace:
        trace.step("send", "enter sent", f"compose_empty={'yes' if not remaining else 'no'}")

    if remaining:
        button, button_selector = _first_visible(page, SEND_BUTTONS)
        if button:
            try:
                button.click()
                time.sleep(1.5)
                if trace:
                    trace.step("send", "fallback", f"selector={button_selector} | clicked")
            except Exception as exc:
                if trace:
                    trace.fail("send", "send", f"{type(exc).__name__}: {exc}")
                return False
        else:
            if trace:
                trace.fail("send", "send", "text still present and no send button found")
            return False
    elif trace:
        trace.step("send", "fallback", "not needed")

    # Ported confirmation step: look for our own message in the conversation.
    # If WhatsApp has not rendered the container yet, accept the send rather
    # than blocking the campaign on a cosmetic check.
    try:
        last_message = page.query_selector('div[data-testid="msg-container"]:last-child')
        if last_message:
            own = last_message.query_selector('div[data-testid="msg-own"]')
            if trace:
                trace.step(
                    "send",
                    "confirmed",
                    f'selector=div[data-testid="msg-container"]:last-child | own={"yes" if own else "no"}',
                )
            if trace:
                trace.step("send", "MESSAGE SENT SUCCESSFULLY")
            return True
        if trace:
            trace.step("send", "not confirmed", "no msg-container found; assuming sent")
    except Exception as exc:
        if trace:
            trace.step(
                "send",
                "not confirmed",
                f"{type(exc).__name__}: {exc}; assuming sent",
            )

    if trace:
        trace.step("send", "MESSAGE SENT SUCCESSFULLY")
    return True


# ── public posting API ──────────────────────────────────────────────────


def post_text(
    bot: WhatsAppBot,
    target: str,
    text: str,
    context: str = "group",
    on_event: EventCallback = None,
    should_skip: SkipCheck = None,
    trace: Optional[Trace] = None,
    attempts: int = 3,
) -> bool:
    trace = trace or _make_trace(on_event, target, attempts=attempts)

    try:
        if _skip_requested(should_skip):
            trace.skip("skip requested before opening")
            return False

        trace.step("target", "opening chat")
        if not open_chat(bot, target, context, attempts=attempts, trace=trace):
            trace.finish(
                False,
                trace.failure_step or "group",
                trace.failure_detail or "could not open chat",
            )
            return False

        trace.step("target", "chat opened")
        if _skip_requested(should_skip):
            trace.skip("skip requested after opening the chat")
            return False

        if bot.is_definitely_disconnected():
            trace.fail("session", "session", "before typing")
            trace.capture(bot.page, "before_type")
            trace.finish(False, trace.failure_step or "session", "WhatsApp connection lost before typing")
            return False

        trace.step("target", "typing message")
        if not _type_text(bot, text, trace=trace):
            trace.finish(False, trace.failure_step or "typing", "typing failed")
            return False

        if _skip_requested(should_skip):
            trace.skip("skip requested before sending")
            return False

        if bot.is_definitely_disconnected():
            trace.fail("session", "session", "before sending")
            trace.capture(bot.page, "before_send")
            trace.finish(False, trace.failure_step or "session", "WhatsApp connection lost before sending")
            return False

        trace.step("target", "waiting for link preview")
        _wait_for_link_preview(bot, text, trace=trace)

        trace.step("target", "sending")
        ok = _press_send(bot, trace=trace)
        if ok:
            trace.finish(True, "send")
            bot.human_delay()
        else:
            trace.finish(False, trace.failure_step or "send", "send could not be confirmed")
        return ok
    except Exception as exc:
        trace.fail("target", "exception", f"{type(exc).__name__}: {exc}")
        try:
            trace.capture(bot.page, "exception")
        except Exception:
            pass
        trace.finish(False, trace.failure_step or "exception", str(exc))
        log("error", f"post_text exception for '{target}': {exc}", "poster")
        return False


def _attach_image(bot: WhatsAppBot, path: Path, trace: Optional[Trace] = None) -> bool:
    page = bot.page
    if trace:
        trace.step("media", "attaching image", f"path={_preview(str(path), 100)}")
    try:
        inputs = page.query_selector_all('input[type="file"]')
        for element in inputs:
            try:
                element.set_input_files(str(path))
                time.sleep(1.5)
                if trace:
                    trace.step("media", "attached")
                return True
            except Exception:
                continue
    except Exception:
        pass

    button, button_selector = _first_visible(page, ATTACH_BUTTONS)
    if not button:
        if trace:
            trace.fail("media", "media", "no file input or attach button found")
        return False
    try:
        with page.expect_file_chooser(timeout=8000) as chooser_info:
            button.click()
        chooser_info.value.set_files(str(path))
        time.sleep(1.5)
        if trace:
            trace.step("media", "attached", f"selector={button_selector}")
        return True
    except Exception as exc:
        if trace:
            trace.fail("media", "media", f"{type(exc).__name__}: {exc}")
        log("warning", f"could not attach image: {exc}", "poster")
        return False


def post_image(
    bot: WhatsAppBot,
    target: str,
    image_path: Path,
    caption: str,
    context: str = "group",
    on_event: EventCallback = None,
    should_skip: SkipCheck = None,
    trace: Optional[Trace] = None,
    attempts: int = 3,
) -> bool:
    trace = trace or _make_trace(on_event, target, attempts=attempts)

    try:
        if _skip_requested(should_skip):
            trace.skip("skip requested before opening")
            return False

        trace.step("target", "opening chat")
        if not open_chat(bot, target, context, attempts=attempts, trace=trace):
            trace.finish(
                False,
                trace.failure_step or "group",
                trace.failure_detail or "could not open chat",
            )
            return False

        trace.step("target", "chat opened")
        if _skip_requested(should_skip):
            trace.skip("skip requested after opening the chat")
            return False

        if bot.is_definitely_disconnected():
            trace.fail("session", "session", "before attaching media")
            trace.capture(bot.page, "before_attach")
            trace.finish(False, trace.failure_step or "session", "WhatsApp connection lost before attaching media")
            return False

        trace.step("target", "attaching image")
        if not _attach_image(bot, image_path, trace=trace):
            log("warning", f"image attach failed for '{target}', falling back to text", "poster")
            trace.step("media", "fallback to text")
            return post_text(
                bot, target, caption, context,
                on_event=on_event, should_skip=should_skip,
                trace=trace, attempts=attempts,
            )

        time.sleep(1.5)
        if caption:
            trace.step("target", "typing caption")
            if not _type_text(bot, caption, prefer_caption=True, trace=trace):
                trace.finish(False, trace.failure_step or "typing", "caption typing failed")
                return False
            trace.step("target", "waiting for link preview")
            _wait_for_link_preview(bot, caption, trace=trace)
        else:
            trace.step("typing", "skipped", "no caption")

        if _skip_requested(should_skip):
            trace.skip("skip requested before sending")
            return False

        if bot.is_definitely_disconnected():
            trace.fail("session", "session", "before sending")
            trace.capture(bot.page, "before_send")
            trace.finish(False, trace.failure_step or "session", "WhatsApp connection lost before sending")
            return False

        trace.step("target", "sending")
        ok = _press_send(bot, trace=trace)
        if ok:
            trace.finish(True, "send")
            bot.human_delay()
        else:
            trace.finish(False, trace.failure_step or "send", "send could not be confirmed")
        return ok
    except Exception as exc:
        trace.fail("target", "exception", f"{type(exc).__name__}: {exc}")
        try:
            trace.capture(bot.page, "exception")
        except Exception:
            pass
        trace.finish(False, trace.failure_step or "exception", str(exc))
        log("error", f"post_image exception for '{target}': {exc}", "poster")
        return False


def post_product(
    bot: WhatsAppBot,
    target: str,
    product: Dict[str, Any],
    text: str,
    context: str = "group",
    on_event: EventCallback = None,
    should_skip: SkipCheck = None,
    trace: Optional[Trace] = None,
    attempts: int = 3,
) -> bool:
    """Send image+caption when the product has media, otherwise text."""
    media_path = resolve_media_path(product.get("media_url"))
    if media_path:
        return post_image(
            bot, target, media_path, text, context,
            on_event=on_event, should_skip=should_skip, trace=trace, attempts=attempts,
        )
    return post_text(
        bot, target, text, context,
        on_event=on_event, should_skip=should_skip, trace=trace, attempts=attempts,
    )


# ── media ───────────────────────────────────────────────────────────────


def resolve_media_path(media_url: Optional[str]) -> Optional[Path]:
    """Turn /uploads/x, an http URL or a local path into an existing file."""
    if not media_url:
        return None
    value = str(media_url).strip()
    if not value:
        return None

    if value.startswith("/uploads/"):
        candidate = UPLOAD_DIR / Path(value).name
        return candidate if candidate.is_file() else None

    if value.lower().startswith(("http://", "https://")):
        cache_dir = Path(tempfile.gettempdir()) / "marketing_bot_media"
        cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(value.split("?")[0]).suffix or ".jpg"
        target = cache_dir / (hashlib.sha1(value.encode()).hexdigest() + suffix)
        if target.is_file() and target.stat().st_size > 0:
            return target
        try:
            with urllib.request.urlopen(value, timeout=25) as response:
                target.write_bytes(response.read())
            return target if target.stat().st_size > 0 else None
        except Exception as exc:
            log("warning", f"could not download image {value}: {exc}", "poster")
            return None

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate if candidate.is_file() else None
