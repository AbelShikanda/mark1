"""Idempotent product seeder.

Reads the adoption exports in ``backend/adopt/products/*.json`` (or paths given
on the command line) and imports them as products.

Mapping rules
-------------
- ``link`` is the source ``url``; candidates with a non-http(s) link are skipped.
- WhatsApp products keep their ``product_name`` verbatim and use the category
  ``whatsapp``. A source status of ``posted`` becomes ``isPosted`` (with
  ``posted_at``/``last_posted_at`` taken from ``posted_date`` + ``posted_time``);
  everything else becomes ``isNotPosted``.
- Instagram items have no captions in the exports, so they are named
  ``Instagram Reel <id>`` / ``Instagram Post <id>`` and use the category
  ``instagram``. By default they are all imported as ``isNotPosted`` because the
  source "posted" flag describes Instagram, not WhatsApp. Pass
  ``--preserve-status`` to keep the source status instead.
- ``description`` is ``None`` unless an Instagram caption is present.
- ``media_url`` is always ``None``; the source page URL is not media.
- ``scheduled_date`` / ``scheduled_time`` are ignored: campaigns own scheduling.

Deduplication is by exact link (no query/trailing-slash normalisation). Existing
products are never overwritten: only blank ``name``, ``description``,
``category`` and ``media_url`` fields are filled in. Products absent from the
source files are never deleted, so re-running is safe and deleted rows stay
deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from db_logic import get_conn, init_db, log

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_SEED_DIR = BACKEND_DIR / "adopt" / "products"

WHATSAPP = "whatsapp"
INSTAGRAM = "instagram"

INSERT_SQL = (
    "INSERT INTO products "
    "(name, description, media_url, link, category, status, posted_at, last_posted_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))"
)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_http_link(value: Any) -> bool:
    link = _text(value).lower()
    return link.startswith("http://") or link.startswith("https://")


def _posted_at(item: Dict[str, Any]) -> Optional[str]:
    """Combine ``posted_date`` + ``posted_time`` into a SQLite timestamp."""
    date = _text(item.get("posted_date"))
    if not date:
        return None
    date = date.split("T")[0]
    time = _text(item.get("posted_time")) or "00:00:00"
    if len(time) == 5:  # HH:MM
        time += ":00"
    return f"{date} {time}"


def _source_kind(path: Path, data: Dict[str, Any]) -> Optional[str]:
    if isinstance(data.get("products"), list):
        return WHATSAPP
    if isinstance(data.get("reels"), list):
        return INSTAGRAM
    # Instagram exports may have only a "posts" list; LinkedIn exports have the
    # same key but no usable data, so rely on the filename here.
    if "instagram" in path.name.lower() and isinstance(data.get("posts"), list):
        return INSTAGRAM
    return None


def load_source(path: Path) -> Tuple[Optional[str], Dict[str, Any]]:
    """Load one JSON file and return ``(kind, data)``; kind is None if unsupported."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("source file must contain a JSON object")
    return _source_kind(Path(path), data), data


def _source_items(kind: str, data: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str]]:
    """Return ``(item, media_type)`` pairs for a source document."""
    if kind == WHATSAPP:
        return [(item, WHATSAPP) for item in data.get("products") or []]
    items: List[Tuple[Dict[str, Any], str]] = []
    for item in data.get("reels") or []:
        media_type = _text(item.get("media_type")) or "reel"
        items.append((item, media_type))
    for item in data.get("posts") or []:
        media_type = _text(item.get("media_type")) or "post"
        items.append((item, media_type))
    return items


def _build_candidate(
    item: Dict[str, Any],
    kind: str,
    media_type: str,
    source_name: str,
    preserve_status: bool,
    all_pending: bool,
) -> Optional[Dict[str, Any]]:
    link = _text(item.get("url"))
    item_id = _text(item.get("id"))

    if kind == WHATSAPP:
        name = _text(item.get("product_name"))
        if not name:
            return None
        category = WHATSAPP
        description = None
        source_posted = _text(item.get("status")).lower() == "posted"
    else:
        if not item_id:
            return None
        reel = media_type.lower() == "reel"
        name = f"Instagram {'Reel' if reel else 'Post'} {item_id}"
        category = INSTAGRAM
        caption = _text(item.get("caption"))
        description = caption or None
        source_posted = _text(item.get("status")).lower() == "posted"

    if all_pending:
        status = "isNotPosted"
    elif kind == INSTAGRAM and not preserve_status:
        status = "isNotPosted"
    else:
        status = "isPosted" if source_posted else "isNotPosted"

    posted_at = _posted_at(item) if status == "isPosted" else None
    return {
        "name": name,
        "description": description,
        "media_url": None,
        "link": link,
        "category": category,
        "status": status,
        "posted_at": posted_at,
        "last_posted_at": posted_at,
        "source": source_name,
    }


def collect_products(
    sources: Sequence[Tuple[Path, Optional[str], Dict[str, Any]]],
    preserve_status: bool = False,
    all_pending: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, int]]]:
    """Turn loaded sources into unique candidates.

    Duplicate links (within or across sources) are skipped, and invalid links
    are reported as warnings. Later duplicates never replace the first one.
    """
    candidates: List[Dict[str, Any]] = []
    warnings: List[str] = []
    per_source: Dict[str, Dict[str, int]] = {}
    seen_links: set[str] = set()

    for path, kind, data in sources:
        source_name = path.name
        stats = {"candidates": 0, "skipped": 0}
        per_source[source_name] = stats

        if kind is None:
            warnings.append(f"{source_name}: skipped (no WhatsApp products or Instagram items)")
            continue

        for item, media_type in _source_items(kind, data):
            if not isinstance(item, dict):
                stats["skipped"] += 1
                continue
            link = _text(item.get("url"))
            label = _text(item.get("id")) or link or "?"
            if not _is_http_link(link):
                warnings.append(f"{source_name}: skipped {label} with invalid link {link!r}")
                stats["skipped"] += 1
                continue
            if link in seen_links:
                warnings.append(f"{source_name}: skipped duplicate link {link}")
                stats["skipped"] += 1
                continue
            if kind == WHATSAPP and not _text(item.get("product_name")):
                warnings.append(f"{source_name}: skipped {label} without a product_name")
                stats["skipped"] += 1
                continue
            if kind == INSTAGRAM and not _text(item.get("id")):
                warnings.append(f"{source_name}: skipped an Instagram item without an id")
                stats["skipped"] += 1
                continue

            candidate = _build_candidate(
                item, kind, media_type, source_name, preserve_status, all_pending
            )
            if candidate is None:
                stats["skipped"] += 1
                continue
            seen_links.add(link)
            candidates.append(candidate)
            stats["candidates"] += 1

    return candidates, warnings, per_source


def _existing_by_link(conn) -> Dict[str, Any]:
    rows = conn.execute("SELECT * FROM products WHERE link IS NOT NULL").fetchall()
    existing: Dict[str, Any] = {}
    for row in rows:
        existing.setdefault(row["link"], row)
    return existing


def _resolve_paths(paths: Optional[Sequence[str]]) -> List[Path]:
    if not paths:
        if not DEFAULT_SEED_DIR.is_dir():
            return []
        return sorted(DEFAULT_SEED_DIR.glob("*.json"))

    resolved: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            resolved.extend(sorted(path.glob("*.json")))
        else:
            resolved.append(path)
    return resolved


def seed_products(
    paths: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    preserve_status: bool = False,
    all_pending: bool = False,
) -> Dict[str, Any]:
    """Import product candidates and return a summary dictionary.

    ``dry_run`` reports what would happen but writes nothing (no products, no
    logs). Re-running is idempotent: products are matched by exact link.
    """
    files = _resolve_paths(paths)
    explicit_paths = bool(paths)
    summary: Dict[str, Any] = {
        "dry_run": bool(dry_run),
        "preserve_status": bool(preserve_status),
        "all_pending": bool(all_pending),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "total": 0,
        "would_insert": 0,
        "would_update": 0,
        "sources": {},
        "warnings": [],
    }

    if not files:
        summary["warnings"].append("no product seed files found")
        return summary

    sources: List[Tuple[Path, Optional[str], Dict[str, Any]]] = []
    for path in files:
        try:
            kind, data = load_source(path)
        except Exception as exc:
            summary["warnings"].append(f"{path}: could not read seed file: {exc}")
            continue
        if kind is None and not explicit_paths:
            # The default folder may contain unrelated exports (e.g. LinkedIn
            # or Facebook); ignore those silently unless the user named them.
            continue
        sources.append((path, kind, data))

    candidates, warnings, per_source = collect_products(
        sources, preserve_status=preserve_status, all_pending=all_pending
    )
    summary["warnings"].extend(warnings)
    summary["sources"] = per_source
    summary["total"] = len(candidates)

    skipped = sum(stats["skipped"] for stats in per_source.values())
    conn = get_conn()
    try:
        existing = _existing_by_link(conn)

        for candidate in candidates:
            source_stats = per_source[candidate["source"]]
            for key in ("inserted", "updated", "would_insert", "would_update", "unchanged"):
                source_stats.setdefault(key, 0)

            row = existing.get(candidate["link"])
            if row is None:
                summary["would_insert"] += 1
                source_stats["would_insert"] += 1
                if not dry_run:
                    conn.execute(
                        INSERT_SQL,
                        (
                            candidate["name"],
                            candidate["description"],
                            candidate["media_url"],
                            candidate["link"],
                            candidate["category"],
                            candidate["status"],
                            candidate["posted_at"],
                            candidate["last_posted_at"],
                        ),
                    )
                    source_stats["inserted"] += 1
                continue

            changes: List[str] = []
            params: List[Any] = []
            for column in ("name", "description", "category", "media_url"):
                source_value = candidate[column]
                if _is_blank(source_value) or not _is_blank(row[column]):
                    continue
                changes.append(f"{column} = ?")
                params.append(source_value)

            if not changes:
                skipped += 1
                source_stats["unchanged"] += 1
                continue

            summary["would_update"] += 1
            source_stats["would_update"] += 1
            if not dry_run:
                params.append(row["id"])
                conn.execute(
                    f"UPDATE products SET {', '.join(changes)}, updated_at = datetime('now') "
                    "WHERE id = ?",
                    tuple(params),
                )
                source_stats["updated"] += 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    if dry_run:
        summary["skipped"] = skipped
    else:
        summary["inserted"] = summary["would_insert"]
        summary["updated"] = summary["would_update"]
        # ``skipped`` also covers unchanged existing rows, matching the group
        # seeder's meaning of "nothing needed doing".
        summary["skipped"] = skipped

    if not dry_run:
        for warning in summary["warnings"]:
            log("warning", warning, "seeder")
        log(
            "info",
            "product seed: "
            f"{summary['inserted']} inserted, {summary['updated']} updated, "
            f"{summary['skipped']} skipped, {summary['total']} candidates",
            "seeder",
        )
        for name, stats in summary["sources"].items():
            log(
                "info",
                f"product seed {name}: "
                f"{stats.get('candidates', 0)} candidates, "
                f"{stats.get('inserted', 0)} inserted, "
                f"{stats.get('updated', 0)} updated, "
                f"{stats.get('unchanged', 0)} unchanged",
                "seeder",
            )

    return summary


def _print_summary(summary: Dict[str, Any]) -> None:
    mode = "DRY RUN" if summary["dry_run"] else "SEED"
    print(f"[{mode}] products: {summary['total']} candidates")
    print(
        f"  inserted={summary['inserted']} updated={summary['updated']} "
        f"skipped={summary['skipped']}"
        + (
            f" (would insert={summary['would_insert']}, would update={summary['would_update']})"
            if summary["dry_run"]
            else ""
        )
    )
    for name, stats in summary["sources"].items():
        parts = [f"candidates={stats.get('candidates', 0)}"]
        keys = ["inserted", "updated", "would_insert", "would_update", "unchanged", "skipped"]
        for key in keys:
            if key in stats and (summary["dry_run"] or not key.startswith("would_")):
                parts.append(f"{key}={stats[key]}")
        print(f"  {name}: " + ", ".join(parts))
    for warning in summary["warnings"]:
        print(f"  warning: {warning}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotently seed products from JSON exports.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="JSON files or directories (default: backend/adopt/products/*.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report without writing anything")
    parser.add_argument(
        "--preserve-status",
        action="store_true",
        help="keep Instagram items marked posted in the source (default: all isNotPosted)",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="import every product as isNotPosted, even posted WhatsApp products",
    )
    args = parser.parse_args(argv)

    try:
        init_db()
        summary = seed_products(
            args.paths or None,
            dry_run=args.dry_run,
            preserve_status=args.preserve_status,
            all_pending=args.all_pending,
        )
    except Exception as exc:  # keep CLI failures readable
        print(f"product seed failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
