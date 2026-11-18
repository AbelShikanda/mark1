"""Offline message classification.

Keyword-based heuristics in English / Swahili / Sheng. No external calls, no
models: every captured message is tagged at capture time. Nothing here is
ground truth — it exists so dashboards and spam review have a reasonable
first pass that a human can correct.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Tuple

from db_logic import get_conn

# ── intent lexicon ───────────────────────────────────────────────────────

_INTENT_PATTERNS: Dict[str, List[str]] = {
    "price": [
        r"\bbei\b", r"\bbeije\b", r"\bprice\b", r"\bcost\b", r"\bksh\b", r"\bkshs\b", r"\bkes\b",
        r"\bshs\b", r"\bhow much\b", r"\bmata\b", r"\bcharging\b", r"\bafford\b",
        r"\bwhat'?s the price\b", r"\bbei gani\b", r"\b bei\b",
    ],
    "availability": [
        r"\bavailable\b", r"\bavailability\b", r"\bin stock\b", r"\bnataka\b", r"\b nataka\b",
        r"\bina\b", r"\biti\b", r"\bistock\b", r"\bstock\b", r"\bcan i (get|buy)\b", r"\biko\b",
        r"\bile\b", r"\bhas\b", r"\bstill have\b",
    ],
    "location": [
        r"\bwapi\b", r"\bwhere\b", r"\blocation\b", r"\bmahali\b", r"\bduka\b", r"\bshop\b",
        r"\bbranch\b", r"\bwhich (shop|store)\b", r"\bhow to (get there|find)\b",
        r"\badministrative\b", r"\bmtaa\b", r"\barea\b",
    ],
    "delivery": [
        r"\bdeliver\b", r"\bdelivery\b", r"\btm\b", r"\bsend\b", r"\bcourier\b", r"\bship\b",
        r"\bshipping\b", r"\bnikienda\b", r"\bdrop\b", r"\bbring\b", r"\bmail\b",
    ],
    "order": [
        r"\bnataka\b", r"\bnituma\b", r"\bnitatumia\b", r"\bnigga\b", r"\border\b", r"\borda\b",
        r"\bbook\b", r"\bbuy\b", r"\bwant\b", r"\bsend mine\b", r"\bnipeleke\b", r"\bnitaka\b",
        r"\bpick up\b", r"\bpickup\b", r"\bnalipay\b", r"\bloan\b", r"\bclick\b",
    ],
    "complaint": [
        r"\bmbovu\b", r"\bmbaya\b", r"\bbad\b", r"\bwrong\b", r"\bproblem\b", r"\bissue\b",
        r"\bdamaged\b", r"\bfault\b", r"\bnot working\b", r"\bscam\b", r"\bfake\b",
    ],
    "compliment": [
        r"\basante\b", r"\bthanks\b", r"\bgood\b", r"\bnice\b", r"\bgreat\b", r"\blove\b",
        r"\bexcellent\b", r"\bsafi\b", r"\bpoa\b", r"\bgood job\b", r"\bfantastic\b",
    ],
    "greeting": [
        r"\bhello\b", r"\bhi\b", r"\bmorning\b", r"\bevening\b", r"\bmambo\b", r"\bjipende\b",
        r"\bgood morning\b", r"\bgood evening\b", r"\bhabari\b", r"\bjambo\b",
    ],
}

# ── sentiment lexicon ────────────────────────────────────────────────────

_POSITIVE = {
    "asante", "thanks", "good", "nice", "great", "love", "excellent", "safi", "poa",
    "fantastic", "beautiful", "amazing", "happy", "fair", "solid",
}
_NEGATIVE = {
    "mbovu", "mbaya", "bad", "worse", "wrong", "problem", "issue", "damaged", "fault",
    "scam", "fake", "useless", "poor", "awful", "terrible", "hatari", "hasara",
}

# ── spam / scam lexicon ─────────────────────────────────────────────────

_SPAM_PATTERNS = [
    r"\bregistration fee\b", r"\binvest(ing|ment)\b", r"\bforex\b", r"\bcrypto\b",
    r"\bbitcoin\b", r"\bdoubling\b", r"\bdouble your\b", r"\bmoney doubling\b",
    r"\bcash[\- ]?out\b", r"\bwork from home\b", r"\bearn daily\b", r"\bdaily income\b",
    r"\bpassive income\b", r"\bdm me\b", r"\bpm me\b", r"\bdm me for\b", r"\bwhatsapp me\b",
    r"\bcopy and paste\b", r"\bget rich\b", r"\bquick cash\b", r"\bbonus\b", r"\bairdrop\b",
    r"\bmining\b", r"\bnft\b", r"\bsus\b", r"\bclick here\b", r"\bregister now\b",
]

# Words too common to be "keywords".
_STOP = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "is", "are", "be", "it",
    "this", "that", "with", "you", "your", "i", "we", "my", "me", "at", "if", "but",
    "he", "she", "they", "was", "were", "will", "not", "have", "has", "do", "does",
    "can", "could", "should", "u", "your", "our", "so", "as", "by", "or", "just",
    "what", "whats", "when", "how",
    "na", "ya", "wa", "la", "cha", "kwa", "ni", "za", "zao", "wao", "wangu", "mimi",
    "hii", "hiyo", "ile", "hapa", "pale", "na", "au", "kwa", "kwenye", "kama", "lakini",
}

_product_cache: Dict[str, Any] = {"ts": 0.0, "words": []}
_product_ttl = 300.0


def _product_keywords() -> List[str]:
    now = time.time()
    if now - _product_cache["ts"] < _product_ttl and _product_cache["words"]:
        return _product_cache["words"]
    words: set = set()
    try:
        conn = get_conn()
        rows = conn.execute("SELECT name FROM products WHERE name IS NOT NULL").fetchall()
        conn.close()
        for row in rows:
            name = (row["name"] or "").lower()
            for token in re.sub(r"[^a-z0-9 ]+", " ", name).split():
                if len(token) >= 4 and token not in _STOP:
                    words.add(token)
    except Exception:
        words = set()
    _product_cache["words"] = sorted(words)
    _product_cache["ts"] = now
    return _product_cache["words"]


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _first_match(text: str, patterns: List[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify(text: str) -> Dict[str, Any]:
    """Return {intent, sentiment, topics, spam_flag, spam_reason}."""
    norm = _norm(text)
    spam_hit = _first_match(norm, _SPAM_PATTERNS)

    intent = "other"
    # Ordered: most specific patterns win.
    for name in ("price", "availability", "order", "location", "delivery", "complaint", "compliment", "greeting"):
        if _first_match(norm, _INTENT_PATTERNS[name]):
            intent = name
            break

    tokens = set(norm.split())
    pos = len(tokens & _POSITIVE)
    neg = len(tokens & _NEGATIVE)
    sentiment = "positive" if pos > neg else ("negative" if neg > pos else "neutral")

    topics = [word for word in _product_keywords() if word in tokens]

    return {
        "intent": intent,
        "sentiment": sentiment,
        "topics": topics,
        "spam_flag": 1 if spam_hit else 0,
        "spam_reason": "lexicon" if spam_hit else "",
    }


def top_keywords(texts: List[str], limit: int = 25) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for text in texts:
        for token in _norm(text).split():
            if len(token) < 4 or token in _STOP:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def parse_topics(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def json_topics(topics: List[str]) -> str:
    return json.dumps(sorted(set(topics)))
