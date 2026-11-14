"""Idempotent group seeder.

Accepts either:
- ``backend/target_groups.py`` exposing ``CORE_GROUPS``, ``MARKETING_GROUPS``,
  ``GROUP_CATEGORIES`` and optionally ``GROUP_LINKS``; or
- ``data/groups_seed.json`` shaped like::

      {
        "core": ["Group A", {"name": "Group B", "region": "Nairobi", "topic": "business", "link": "https://chat.whatsapp.com/..."}],
        "marketing": ["Group C", ...],
        "categories": {"business": ["Group A", "Group C"]},
        "links": {"Group A": "https://chat.whatsapp.com/..."}
      }

Rules:
- duplicate names are removed case-insensitively (core wins over marketing);
- target groups default to ``n = 1``;
- core groups become ``is_core = 1`` and ``is_my_group = 1`` (link sources);
- region is taken from an explicit field or matched against known Kenyan
  locations in the name; topic/category comes from the category map or a
  keyword classifier;
- existing rows are never overwritten destructively: only missing metadata is
  filled, so edits made in the UI survive re-seeding.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import DATA_DIR
from db_logic import get_conn, log

SEED_JSON = DATA_DIR / "groups_seed.json"
BACKEND_DIR = Path(__file__).resolve().parent
ADOPT_DIR = BACKEND_DIR / "adopt"


def _load_target_groups():
    """Load ``target_groups.py`` from backend/ or backend/adopt/.

    The supplied reference files live in ``backend/adopt``; a copy dropped
    directly into ``backend/`` takes precedence so the user can override it.
    """
    for folder in (BACKEND_DIR, ADOPT_DIR):
        candidate = folder / "target_groups.py"
        if not candidate.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("target_groups", candidate)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules["target_groups"] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            log("warning", f"could not load {candidate}: {exc}", "seeder")
    try:
        import target_groups  # type: ignore

        return target_groups
    except Exception:
        return None

REGION_ALIASES = [
    "athi river", "juja", "ruiru", "kasarani", "westlands", "kilimani", "karen",
    "rongai", "kitengela", "ngong", "naivasha", "nakuru", "eldoret", "kisumu",
    "mombasa", "nyali", "diani", "kilifi", "watamu", "malindi", "lamu",
    "thika", "kakamega", "bungoma", "kitale", "kisii", "kericho", "bomet",
    "narok", "meru", "embu", "nyeri", "machakos", "kitui", "voi", "garissa",
    "wajir", "mandera", "isiolo", "marsabit", "lodwar", "kajiado", "nairobi",
]

TOPIC_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("property", ["property", "real estate", "land", "plots", "houses", "rentals"]),
    ("automotive", ["car", "cars", "motor", "vehicle", "matatu", "bike", "automotive"]),
    ("fashion", ["fashion", "clothes", "clothing", "boutique", "beauty", "salon", "thrift"]),
    ("electronics", ["tech", "electronic", "phone", "laptop", "gadget", "computer"]),
    ("education", ["education", "school", "college", "university", "learning", "tutor"]),
    ("jobs", ["job", "jobs", "vacancy", "career", "employment", "hiring"]),
    ("business", ["business", "entrepreneur", "trade", "market", "sales", "shop"]),
    ("health", ["health", "hospital", "clinic", "doctor", "fitness", "gym"]),
    ("food", ["food", "restaurant", "cafe", "kitchen", "cook", "baking"]),
    ("music", ["music", "dj", "band", "audio"]),
    ("entertainment", ["movies", "entertainment", "comedy", "gaming", "games"]),
    ("religion", ["church", "christian", "muslim", "mosque", "faith", "prayer"]),
    ("politics", ["politics", "political", "county", "government"]),
    ("sports", ["sports", "football", "soccer", "betting", "athletics"]),
    ("travel", ["travel", "tours", "tourism", "trips", "safari"]),
    ("agriculture", ["farm", "agriculture", "farming", "livestock", "crops"]),
    ("marketing", ["marketing", "advert", "promo", "groups", "links"]),
]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _dedupe_key(name: str) -> str:
    return _clean(name).lower()


def detect_region(name: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return _clean(explicit).title()
    lowered = _clean(name).lower()
    for region in REGION_ALIASES:
        if re.search(rf"\b{re.escape(region)}\b", lowered):
            return region.title()
    return None


def detect_topic(name: str, explicit: Optional[str] = None, reverse_map: Optional[Dict[str, str]] = None) -> str:
    if explicit:
        return _clean(explicit).lower()
    key = _dedupe_key(name)
    if reverse_map and key in reverse_map:
        return reverse_map[key]
    lowered = key
    for topic, keywords in TOPIC_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return topic
    return "general"


def _normalise_entry(entry: Any, category: Optional[str]) -> Dict[str, Any]:
    if isinstance(entry, dict):
        name = _clean(entry.get("name") or entry.get("group") or entry.get("title"))
        return {
            "name": name,
            "region": entry.get("region") or entry.get("location"),
            "topic": entry.get("topic") or entry.get("category") or category,
            "link": entry.get("link") or entry.get("url"),
        }
    return {"name": _clean(entry), "region": None, "topic": category, "link": None}


def load_seed_source(path: Optional[Path] = None) -> Dict[str, Any]:
    """Return {'core': [...], 'marketing': [...], 'categories': {...}, 'links': {...}}."""
    if path and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "core": data.get("core", []),
            "marketing": data.get("marketing", []),
            "categories": data.get("categories", {}),
            "links": data.get("links", {}),
        }

    # Prefer a dropped-in target_groups.py (the user's original seed file),
    # including the supplied reference copy in backend/adopt/.
    target_groups = _load_target_groups()
    if target_groups is not None:
        return {
            "core": getattr(target_groups, "CORE_GROUPS", []),
            "marketing": getattr(target_groups, "MARKETING_GROUPS", []),
            "categories": getattr(target_groups, "GROUP_CATEGORIES", {}),
            "links": getattr(target_groups, "GROUP_LINKS", {}),
        }

    if SEED_JSON.is_file():
        data = json.loads(SEED_JSON.read_text(encoding="utf-8"))
        return {
            "core": data.get("core", []),
            "marketing": data.get("marketing", []),
            "categories": data.get("categories", {}),
            "links": data.get("links", {}),
        }
    return {"core": [], "marketing": [], "categories": {}, "links": {}}


def _reverse_categories(categories: Dict[str, Any]) -> Dict[str, str]:
    reverse: Dict[str, str] = {}
    for category, names in (categories or {}).items():
        if not isinstance(names, (list, tuple)):
            continue
        for name in names:
            if isinstance(name, str):
                reverse.setdefault(_dedupe_key(name), str(category).lower())
    return reverse


def _link_for(name: str, links: Any) -> Optional[str]:
    if not links:
        return None
    if isinstance(links, dict):
        value = links.get(name)
        if value is None:
            for key, candidate in links.items():
                if _dedupe_key(key) == _dedupe_key(name):
                    value = candidate
                    break
        return _clean(value) or None
    if isinstance(links, (list, tuple)):
        for item in links:
            if isinstance(item, dict) and _dedupe_key(item.get("name", "")) == _dedupe_key(name):
                return _clean(item.get("link") or item.get("url")) or None
    return None


def collect_groups(seed: Dict[str, Any]) -> List[Dict[str, Any]]:
    reverse = _reverse_categories(seed.get("categories") or {})
    links = seed.get("links") or {}
    seen: Dict[str, Dict[str, Any]] = {}

    def add(entries: Iterable[Any], is_core: bool) -> None:
        for raw in entries or []:
            entry = _normalise_entry(raw, None)
            name = entry["name"]
            if not name:
                continue
            key = _dedupe_key(name)
            if key in seen:
                if is_core:
                    seen[key]["is_core"] = True
                continue
            seen[key] = {
                "name": name,
                "region": detect_region(name, entry.get("region")),
                "topic": detect_topic(name, entry.get("topic"), reverse),
                "link": entry.get("link") or _link_for(name, links),
                "is_core": is_core,
                "is_my_group": is_core,
            }

    add(seed.get("core"), True)
    add(seed.get("marketing"), False)
    return list(seen.values())


def seed_groups(path: Optional[Path] = None) -> Dict[str, int]:
    """Insert missing groups; fill missing metadata on existing ones."""
    seed = load_seed_source(path)
    groups = collect_groups(seed)
    if not groups:
        log("warning", "group seed is empty; nothing to import", "seeder")
        return {"inserted": 0, "updated": 0, "skipped": 0}

    conn = get_conn()
    existing = {
        _dedupe_key(row["name"]): dict(row)
        for row in conn.execute("SELECT * FROM groups").fetchall()
    }

    inserted = updated = skipped = 0
    for group in groups:
        key = _dedupe_key(group["name"])
        row = existing.get(key)
        if row is None:
            conn.execute(
                "INSERT INTO groups (name, category, location, n, link, is_my_group, is_core) "
                "VALUES (?, ?, ?, 1, ?, ?, ?)",
                (
                    group["name"], group["topic"], group["region"], group["link"],
                    1 if group["is_my_group"] else 0, 1 if group["is_core"] else 0,
                ),
            )
            inserted += 1
            continue

        changes = []
        params: List[Any] = []
        if not row.get("category") and group["topic"]:
            changes.append("category = ?")
            params.append(group["topic"])
        if not row.get("location") and group["region"]:
            changes.append("location = ?")
            params.append(group["region"])
        if not row.get("link") and group["link"]:
            changes.append("link = ?")
            params.append(group["link"])
        if group["is_core"] and not row.get("is_core"):
            changes.append("is_core = 1")
        if group["is_my_group"] and not row.get("is_my_group"):
            changes.append("is_my_group = 1")
        if changes:
            params.append(row["id"])
            conn.execute(f"UPDATE groups SET {', '.join(changes)} WHERE id = ?", tuple(params))
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    log(
        "info",
        f"group seed: {inserted} inserted, {updated} updated, {skipped} unchanged",
        "seeder",
    )
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "total": len(groups)}


def has_seed_source() -> bool:
    target_groups = _load_target_groups()
    if target_groups is not None and (
        getattr(target_groups, "CORE_GROUPS", []) or getattr(target_groups, "MARKETING_GROUPS", [])
    ):
        return True
    if SEED_JSON.is_file():
        try:
            data = json.loads(SEED_JSON.read_text(encoding="utf-8"))
            return bool(data.get("core") or data.get("marketing"))
        except Exception:
            return False
    return False


def maybe_seed_groups() -> Optional[Dict[str, int]]:
    """Seed whenever a source file is present; the import is idempotent."""
    if not has_seed_source():
        return None
    return seed_groups()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(seed_groups(target))
