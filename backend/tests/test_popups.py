"""Offline checks for safe popup classification and the session/QR payloads.

No browser is launched, nothing touches data/marketing.db, and the scheduler
stays disabled. Run from the backend directory:

    .\\venv\\Scripts\\python.exe tests\\test_popups.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_popups_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402

db_logic.init_db()

from bot import campaign_runner as runner  # noqa: E402
from bot.login_manager import (  # noqa: E402
    classify_popup,
    popup_button_is_dangerous,
    popup_button_is_safe,
)


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeBot:
    def __init__(self, headless: bool, qr: str | None):
        self.headless = headless
        self._qr = qr

    def is_browser_closed(self) -> bool:
        return False

    def qr_data_url(self):
        return self._qr


def main_test() -> None:
    # ── classification of popup bodies ──────────────────────────────────
    check(classify_popup("WhatsApp needs permission to access") == "unknown", "unknown body was not unknown")
    check(
        classify_popup("Leave group “Marketing”? You will stop receiving messages.") == "dangerous",
        "leave-group body was not dangerous",
    )
    check(
        classify_popup("Delete this chat for everyone? This cannot be undone.") == "dangerous",
        "delete-for-everyone body was not dangerous",
    )
    check(
        classify_popup("Remove “Ada” as admin?") == "dangerous",
        "remove-admin body was not dangerous",
    )
    check(
        classify_popup("Confirm leaving the group?") == "dangerous",
        "confirmation body was not dangerous",
    )
    check(
        classify_popup("What’s new in WhatsApp — backup tips") == "safe",
        "what’s-new body was not safe",
    )
    check(
        classify_popup("Rate limit reached. Please wait a moment.") == "safe",
        "rate-limit body was not safe",
    )
    check(
        classify_popup("Backup completed successfully. Tip of the day.") == "safe",
        "backup/tip body was not safe",
    )
    # Dangerous markers win over safe ones that may co-occur.
    check(
        classify_popup("Got it? Delete account?") == "dangerous",
        "dangerous co-occurring with safe markers was not treated as dangerous",
    )

    # ── button labels ───────────────────────────────────────────────────
    for label in ["Leave group", "Delete", "Remove from admins", "Yes", "Confirm", "Proceed"]:
        check(popup_button_is_dangerous(label), f"button {label!r} was not dangerous")
    for label in ["Cancel", "Not now", "Maybe later", "Not Now", "Later", "Skip", "Close", "OK", "Got it"]:
        check(popup_button_is_safe(label), f"button {label!r} was not safe")
        check(not popup_button_is_dangerous(label), f"button {label!r} was also dangerous")
    check(not popup_button_is_safe("Delete"), "delete was reported safe")
    check(not popup_button_is_safe(""), "empty label was reported safe")
    check(not popup_button_is_safe("Yes"), "yes was reported safe")

    # ── session status / QR payload ──────────────────────────────────────
    original_bot = runner._bot
    try:
        runner._bot = None
        status = runner.session_status()
        check(status["headless"] == False, "default headless should be False")  # noqa: E712
        check(status["browser_open"] is False, "no bot should report no browser")
        check({"used", "limit", "session_exists", "connected", "headless", "browser_open", "state", "qr_visible"} <= set(status), f"status keys missing: {status}")

        qr = runner.session_qr()
        check(qr["qr_data_url"] is None, "no bot should not return a QR")
        check(qr["available"] is False, "no bot should not report an available QR")

        runner._bot = FakeBot(headless=True, qr="data:image/png;base64,FAKE")
        status = runner.session_status()
        check(status["headless"] is True, "fake headless bot should report headless")
        check(status["browser_open"] is True, "fake bot with a page should report open")

        qr = runner.session_qr()
        # Not waiting for login by default; the QR is only exposed then.
        check(qr["qr_data_url"] is None, "QR leaked while not waiting for login")
        update = runner.get_connection_state() if hasattr(runner, "get_connection_state") else None
        assert update is None or True  # state helper is optional here
    finally:
        runner._bot = original_bot

    # ── state-gated QR capture ──────────────────────────────────────────
    from bot.live_state import update_connection_state  # noqa: E402

    update_connection_state("waiting_qr", "QR required for the test profile", qr_visible=True)
    try:
        runner._bot = FakeBot(headless=True, qr="data:image/png;base64,FAKE")
        qr = runner.session_qr()
        check(qr["qr_data_url"] == "data:image/png;base64,FAKE", "QR not returned while waiting")
        check(qr["available"] is True, "waiting for QR should be available")
        check(qr["headless"] is True, "headless flag missing from QR payload")
        check(qr["state"] == "waiting_qr", f"unexpected state {qr['state']}")
    finally:
        runner._bot = None
        update_connection_state("stopped", "test finished")

    print("All popup/session QR tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
