"""Offline checks for the QR-after-N-runs session settings.

Runs against a throwaway database and session directory selected through
environment variables. It never touches data/marketing.db, never launches
WhatsApp/Playwright/Chrome and never starts the scheduler.

    cd backend
    .\\venv\\Scripts\\python.exe tests\\test_settings_session.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="marketing_settings_session_"))
os.environ["DB_PATH"] = str(TEMP_DIR / "test.db")
os.environ["DATA_DIR"] = str(TEMP_DIR / "data")
os.environ["UPLOAD_DIR"] = str(TEMP_DIR / "uploads")
os.environ["WHATSAPP_SESSION_DIR"] = str(TEMP_DIR / "session")
os.environ["DISABLE_SCHEDULER"] = "1"

import db_logic  # noqa: E402

db_logic.init_db()

from config import SESSION_DIR  # noqa: E402
from bot import settings as app_settings  # noqa: E402
from bot import campaign_runner as runner  # noqa: E402


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def marker() -> Path:
    path = SESSION_DIR / "session-marker.txt"
    path.write_text("saved profile", encoding="utf-8")
    return path


def main_test() -> None:
    # ── qr_after_logins default + clamping ─────────────────────────────
    values = app_settings.get_values()
    check(values.get("qr_after_logins") == 5, f"default should be 5: {values.get('qr_after_logins')}")

    app_settings.update_settings({"qr_after_logins": 0})
    check(
        app_settings.get_int("qr_after_logins") == 1,
        "qr_after_logins below the minimum was not clamped to 1",
    )
    app_settings.update_settings({"qr_after_logins": 1000})
    check(
        app_settings.get_int("qr_after_logins") == 100,
        "qr_after_logins above the maximum was not clamped to 100",
    )
    app_settings.update_settings({"qr_after_logins": 2})
    check(app_settings.get_int("qr_after_logins") == 2, "qr_after_logins did not save 2")

    # ── session_runs_used get/set ──────────────────────────────────────
    check(
        app_settings.get_meta_int("session_runs_used", 0) == 0,
        "session_runs_used should start at 0",
    )
    app_settings.set_meta_int("session_runs_used", 3)
    check(
        app_settings.get_meta_int("session_runs_used", 0) == 3,
        "session_runs_used did not persist 3",
    )

    # ── N=1 clears the profile before every run ────────────────────────
    app_settings.update_settings({"qr_after_logins": 1})
    app_settings.set_meta_int("session_runs_used", 0)
    saved = marker()
    info = runner.prepare_session_for_run()
    check(info["cleared"] is True, f"N=1 should clear the session: {info}")
    check(info["limit"] == 1, f"N=1 limit wrong: {info}")
    check(not saved.exists(), "N=1 did not delete the saved session contents")
    check(
        app_settings.get_meta_int("session_runs_used", 0) == 0,
        "N=1 did not reset session_runs_used",
    )

    # ── N=2 reuses the profile for the first two runs ──────────────────
    app_settings.update_settings({"qr_after_logins": 2})
    app_settings.set_meta_int("session_runs_used", 0)
    saved = marker()
    info = runner.prepare_session_for_run()
    check(info["cleared"] is False, f"N=2 first run should keep the session: {info}")
    check(saved.exists(), "N=2 first run deleted the saved session")
    check(
        app_settings.get_meta_int("session_runs_used", 0) == 0,
        "prepare_session_for_run must not increment the run counter itself",
    )

    app_settings.set_meta_int("session_runs_used", 1)
    info = runner.prepare_session_for_run()
    check(info["cleared"] is False, f"N=2 second run should keep the session: {info}")
    check(saved.exists(), "N=2 second run deleted the saved session")

    # The runner would now have incremented to 2; the next prepare clears.
    app_settings.set_meta_int("session_runs_used", 2)
    info = runner.prepare_session_for_run()
    check(info["cleared"] is True, f"N=2 at the limit should clear the session: {info}")
    check(not saved.exists(), "N=2 at the limit did not delete the saved session")
    check(
        app_settings.get_meta_int("session_runs_used", 0) == 0,
        "N=2 at the limit did not reset session_runs_used",
    )

    # ── status payload + explicit reset ────────────────────────────────
    app_settings.update_settings({"qr_after_logins": 5})
    app_settings.set_meta_int("session_runs_used", 2)
    status = runner.session_status()
    check(status["used"] == 2 and status["limit"] == 5, f"unexpected session status {status}")
    check("session_exists" in status and "connected" in status, f"status keys missing: {status}")

    saved = marker()
    reset = runner.reset_session()
    check(reset["used"] == 0, f"reset did not clear the run counter: {reset}")
    check(not saved.exists(), "reset did not delete the saved session contents")

    print("All settings/session tests passed.")


if __name__ == "__main__":
    try:
        main_test()
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
