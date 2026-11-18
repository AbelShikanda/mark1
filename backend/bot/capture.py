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
]
MSG_TEXT = [
    'div[data-testid="message-text"]',
    '#main div[data-testid="message-text"]',
    'div[data-testid="message-caption"]',
]
MSG_AUTHOR = [
    'div[data-testid="msg-author"]',
    '#main div[data-testid="msg-author"]',
    'span[data-testid="quoted-msg-title"]',
]
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
    if not containers:
        return []

    rows: List[Dict[str, Any]] = []
    for container in containers:
        if len(rows) >= limit:
            break
        try:
            text_el = container.query_selector("div[data-testid=\"message-text\"]")
            if not text_el:
                text_el = container.query_selector("div[data-testid=\"message-caption\"]")
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

    # Cancel-aware dwell: stay out of the way of Stop.
    elapsed = 0.0
    while elapsed < dwell:
        time.sleep(0.5)
        elapsed += 0.5
        try:
            if bot is not None and bot.cancel_event is not None and bot.cancel_event.is_set():
                return 0
        except Exception:
            return 0

    page = getattr(bot, "page", None)
    if page is None:
        return 0

    rows = _scrape_visible(page, limit=40)
    if not rows:
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
    return stored


def _get_campaign(campaign_id: int) -> Optional[Dict[str, Any]]:
    try:
        conn = get_conn()
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None
