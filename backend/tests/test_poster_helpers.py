"""Offline checks for the poster search/header/read-only helpers.

Uses a throwaway database and never launches WhatsApp, Playwright or Chrome.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_poster_helpers.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_poster_helpers_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402

db_logic.init_db()

from bot import poster  # noqa: E402


class FakeElement:
    def __init__(self, text: str = "", title: str | None = None) -> None:
        self.text = text
        self.title = title

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str | None:
        return self.title if name == "title" else None


class FakePage:
    def __init__(self, elements: dict[str, FakeElement]) -> None:
        self.elements = elements

    def query_selector(self, selector: str) -> FakeElement | None:
        return self.elements.get(selector)


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main_test() -> None:
    # ── read-only footer detection ─────────────────────────────────────
    blocked = "You can't send messages to this group because you're no longer a member."
    page = FakePage(
        {
            '#main [data-testid="block-message"]': FakeElement(blocked),
        }
    )
    reason = poster._read_only_reason(page)
    check("no longer a member" in reason, f"read-only footer not detected: {reason!r}")

    typographic = "You can\u2019t send messages to this group because you\u2019re no longer a member."
    page = FakePage(
        {
            '#main [data-testid="block-message"]': FakeElement(typographic),
        }
    )
    check(
        poster._read_only_reason(page),
        "read-only footer with typographic apostrophes was not detected",
    )

    writable = FakePage(
        {
            '#main footer[data-testid="compose-box"]': FakeElement(""),
        }
    )
    check(poster._read_only_reason(writable) == "", "writable footer was treated as read-only")

    # ── conversation header title ──────────────────────────────────────
    header = FakePage(
        {
            'span[data-testid="conversation-info-header-chat-title"]': FakeElement(
                "PRINT SHOP KENYA"
            ),
        }
    )
    check(
        poster._opened_chat_title(header) == "PRINT SHOP KENYA",
        f"header title not read: {poster._opened_chat_title(header)!r}",
    )

    # ── search scoring ────────────────────────────────────────────────
    check(
        poster._candidate_score("print shop kenya", "PRINT SHOP KENYA", "Draft: ELDOR") == 3,
        "exact title should score 3",
    )
    check(
        poster._candidate_score("print shop kenya", "Sunday", "PRINT SHOP KENYA Draft: ELDOR")
        == 0.5,
        "row-text match should score 0.5",
    )
    check(
        poster._candidate_score("print shop kenya", "PRINT SHOP KENYA 2", "") == 2,
        "starts-with title should score 2",
    )

    print("All poster helper tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
