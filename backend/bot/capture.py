"""Capture visible messages in an open chat after a confirmed post.

Runs in the same browser as the posting flow — no extra navigation. Every
failure here is logged and swallowed: capture must never fail a post.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from db_logic import get_conn, log
from . import classifier

# Primary selector first, fallbacks after WhatsApp drifts.
MSG_CONTAINERS = [
    'div[data-testid="msg-container"]',
    '#main div[data-testid="msg-container"]',
    'div[data-testid="msg-own"]',
    '#main div[role="row"]',
    '#main div[data-testid="msg-not-for-me"]',
    '#main li[data-testid^="message-"]',
]
MSG_TEXT = [
    'div[data-testid="message-text"]',
    '#main div[data-testid="message-text"]',
    'div[data-testid="message-caption"]',
    'div[data-testid="caption"]',
    'div[data-testid="msg-text"] > div',
    'span[data-testid="selectable-text"]',
    '#main span[data-testid="selectable-text"]',
]
MSG_AUTHOR = [
    'div[data-testid="msg-author"]',
    '#main div[data-testid="msg-author"]',
    'span[data-testid="quoted-msg-title"]',
    'div[data-testid="msg-author-link"]',
]
MSG_TEXT_ROW = '#main div[data-testid="message-text"], #main div[data-testid="message-caption"], #main span[data-testid="selectable-text"]'
OWN_MARKERS = ['div[data-testid="msg-own"]']

LINK_RE = re.compile(r"(?i)(?:https?://)?(?:www\.)?(chat\.whatsapp\.com/[A-Za-z0-9]{8,})", re.IGNORECASE)
OWN_MESSAGE_TAG = "Me"


def _first_visible(page, selectors: List[str]):
    for selector in selectors:
        try:
            for element in page.query_selector_all(selector):
                try:
                    if element.is_visible():
                        return element
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _sender_of(container, page) -> str:
    # Own messages: WhatsApp renders them in the msg-own wrapper.
    for marker in OWN_MARKERS:
        try:
            own = container.query_selector(marker)
        except Exception:
            own = None
        if own:
            return OWN_MESSAGE_TAG
    for selector in MSG_AUTHOR:
        try:
            el = container.query_selector(selector)
        except Exception:
            el = None
        if el:
            try:
                text = (el.inner_text() or "").strip()
            except Exception:
                text = ""
            if text:
                return text[:120]
    return "unknown"


def _scrape_visible(page, limit: int = 40) -> List[Dict[str, Any]]:
    containers = []
    for selector in MSG_CONTAINERS:
        try:
            containers = page.query_selector_all(selector)
            if containers:
                break
        except Exception:
            containers = []
    if containers:
        rows = _rows_from_containers(page, containers, limit)
        if rows:
            return rows

    # Human fallback: walk message text elements directly, and find each one's
    # owning row so we can still attribute sender/row across WhatsApp builds.
    try:
        texts = page.query_selector_all(MSG_TEXT_ROW)
    except Exception:
        texts = []
    rows: List[Dict[str, Any]] = []
    for text_el in texts:
        if len(rows) >= limit:
            break
        try:
            text = (text_el.inner_text() or "").replace("\n", " ").strip()
            if not text or len(text) > 2000:
                continue
            sender = _sender_from_text_el(page, text_el)
            rows.append({"sender": sender, "text": text})
        except Exception:
            continue
    return rows


def _rows_from_containers(page, containers, limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for container in containers:
        if len(rows) >= limit:
            break
        try:
            text_el = container.query_selector("div[data-testid=\"message-text\"], div[data-testid=\"message-caption\"], span[data-testid=\"selectable-text\"]")
            if not text_el:
                continue
            text = (text_el.inner_text() or "").replace("\n", " ").strip()
            if not text or len(text) > 2000:
                continue
            sender = _sender_of(container, page)
            rows.append({"sender": sender, "text": text})
        except Exception:
            continue
    return rows


def _sender_from_text_el(page, text_el) -> str:
    # Walk up the DOM looking for an author row or our own marker.
    try:
        result = page.evaluate(
            """(el) => {
                let cur = el;
                for (let depth = 0; depth < 8 && cur; depth += 1) {
                    const t = (cur.getAttribute && (cur.getAttribute('data-testid') || '')) || '';
                    if (t.includes('msg-own')) return 'Me';
                    const author = cur.querySelector && cur.querySelector('[data-testid="msg-author"]');
                    if (author && author.innerText && author.innerText.trim()) return author.innerText.trim().slice(0, 120);
                    cur = cur.parentElement;
                }
                return 'unknown';
            }""",
            text_el,
        )
        return str(result)[:120] if result else 'unknown'
    except Exception:
        return 'unknown'


def normalize_link(link: str) -> Optional[str]:
    match = LINK_RE.search(link or "")
    if not match:
        return None
    return match.group(1).lower()


def _upsert_vault(conn, normalized: str, source: str, group_id: Optional[int]) -> None:
    conn.execute(
        "INSERT INTO group_link_vault (normalized_link, source, group_id, first_seen, last_seen, seen_count) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now'), 1) "
        "ON CONFLICT(normalized_link) DO UPDATE SET "
        "last_seen = datetime('now'), seen_count = seen_count + 1, "
        "group_id = COALESCE(group_link_vault.group_id, excluded.group_id)",
        (normalized, source, group_id),
    )


def capture_post_replies(
    bot,
    campaign_id: int,
    group_id: Optional[int],
    post_id: Optional[int],
    run_id: Optional[int],
) -> int:
    """Wait the dwell window then scrape/store visible messages. Returns rows stored."""
    campaign_row = _get_campaign(campaign_id)
    if not campaign_row or not campaign_row.get("capture_replies"):
        return 0
    dwell = max(0, min(600, int(campaign_row.get("capture_dwell_seconds") or 0)))

    def _emit(level: str, event_type: str, message: str) -> None:
        if run_id is None:
            return
        try:
            from . import run_state
            run_state.record_event(run_id, level, event_type, message, campaign_id=campaign_id)
        except Exception:
            pass

    _emit("info", "capture_started", f"capture enabled; waiting {dwell}s after send")

    # Cancel-aware dwell: stay out of the way of Stop.
    elapsed = 0.0
    while elapsed < dwell:
        time.sleep(0.5)
        elapsed += 0.5
        try:
            if bot is not None and bot.cancel_event is not None and bot.cancel_event.is_set():
                _emit("warning", "capture_cancelled", "capture aborted (run cancelled)")
                return 0
        except Exception:
            _emit("warning", "capture_cancelled", "capture aborted (run cancelled)")
            return 0

    page = getattr(bot, "page", None)
    if page is None:
        _emit("error", "capture_failed", "capture skipped: browser page not available")
        return 0

    rows = _scrape_visible(page, limit=40)
    if not rows:
        _emit("warning", "capture_empty", "capture found no messages in this chat (selectors did not match or no new traffic yet)")
        log("warning", f"campaign {campaign_id}: capture scraped 0 messages "
                        f"(URL={getattr(page, 'url', 'unknown')})", "capture")
        return 0

    stored = 0
    stored_ids: List[int] = []
    conn = get_conn()
    for row in rows:
        sender = row["sender"]
        if sender == OWN_MESSAGE_TAG:
            continue
        classification = classifier.classify(row["text"])
        try:
            cur = conn.execute(
                "INSERT INTO group_messages "
                "(group_id, campaign_post_id, run_id, sender, text, intent, sentiment, topics, spam_flag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    group_id,
                    post_id,
                    run_id,
                    sender,
                    row["text"],
                    classification["intent"],
                    classification["sentiment"],
                    classifier.json_topics(classification["topics"]),
                    classification["spam_flag"],
                ),
            )
            stored += 1
            stored_ids.append(int(cur.lastrowid))
        except Exception as exc:
            log("warning", f"could not store captured message: {exc}", "capture")
            continue

    # Batch-blast heuristic: same text from 3+ distinct senders in this capture
    # is almost certainly spam — flag every copy.
    if stored:
        try:
            cur = conn.execute(
                "SELECT text, COUNT(DISTINCT sender) AS n "
                "FROM group_messages WHERE id IN ({}) "
                "GROUP BY text HAVING n >= 3".format(",".join("?" for _ in stored_ids)),
                tuple(stored_ids),
            )
            blasts = [r["text"] for r in cur.fetchall()]
            for text in blasts:
                conn.execute(
                    "UPDATE group_messages SET spam_flag = 1 "
                    f"WHERE id IN ({','.join('?' for _ in stored_ids)}) AND text = ?",
                    tuple(stored_ids + [text]),
                )
        except Exception as exc:
            log("warning", f"blast detection failed: {exc}", "capture")

    # Vault any chat.whatsapp.com group invite links seen in the capture.
    seen_links: List[str] = []
    for row in rows:
        normalized = normalize_link(row["text"])
        if normalized and normalized not in seen_links:
            seen_links.append(normalized)
    for normalized in seen_links:
        try:
            _upsert_vault(conn, normalized, "capture", group_id)
        except Exception as exc:
            log("warning", f"could not vault link {normalized}: {exc}", "capture")

    conn.commit()
    conn.close()
    if stored:
        log("info", f"captured {stored} message(s) in group {group_id} after post {post_id}", "capture")
        _emit("info", "capture_stored", f"captured {stored} message(s) from the chat (own messages skipped)")
    else:
        _emit("info", "capture_stored", "capture ran but stored no new messages (only own/duplicate messages found)")
    return stored


def _get_campaign(campaign_id: int) -> Optional[Dict[str, Any]]:
    try:
        conn = get_conn()
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None
