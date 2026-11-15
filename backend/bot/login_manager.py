"""WhatsApp Web session manager.

Synchronous Playwright port of the reference LoginManager. The important
difference from a naive "just call goto" approach is that every operation
checks for the *definite* disconnection markers (QR canvas / "phone not
connected") and recovers through a bounded reload/reconnect loop instead of
silently posting into a dead page.

Popup handling is deliberately conservative: it only ever clicks close /
cancel / "not now" style buttons. Anything containing leave / delete / remove
/ confirm is ignored so the bot can never leave a group by accident.
"""

from __future__ import annotations

import base64
import random
import time
from typing import List, Optional

from playwright.sync_api import sync_playwright

from config import (
    CONNECTION_WAIT_TIMEOUT,
    LOGIN_TIMEOUT,
    POST_MAX_DELAY,
    POST_MIN_DELAY,
    SESSION_DIR,
)
from db_logic import log
from . import settings as app_settings
from .live_state import update_connection_state

WHATSAPP_URL = "https://web.whatsapp.com"

CONNECTED_SELECTORS = [
    'div[contenteditable="true"][data-tab="3"]',
    'div[aria-label="Search input textbox"]',
    'div[title="Search input textbox"]',
    'div[aria-label="Chats"]',
    'div[data-testid="chat-list"]',
    'div[data-testid="pane-side"]',
    'div[aria-label="Chat list"]',
    'div[role="tablist"]',
    'div[role="row"]',
]

DISCONNECT_SELECTORS = [
    'canvas[aria-label="Scan me!"]',
    'canvas[aria-label="QR code"]',
    'div[data-testid="qr-container"] canvas',
    'div[data-testid="qr-plain"]',
    'div[data-testid="phone-not-connected"]',
    'div[aria-label="Phone not connected"]',
]

LOADING_SELECTORS = [
    'div[data-testid="loading"]',
    'div[data-testid="app"] [role="progressbar"]',
    'div[aria-label="Loading"]',
    'div[data-testid="landing-window"]',
]

# WhatsApp shows a full-page "Loading your chats [15%]" screen while the
# message store downloads. It has no #side yet, so without this text check the
# connection state looks "unknown" and a campaign can start searching too early.
LOADING_TEXT = [
    "loading your chats",
    "messages are downloading",
    "don't close this window",
]

DISCONNECT_TEXT = [
    "phone not connected",
    "scan the qr code",
    "link a device",
    "scan to log in",
]

WELCOME_TEXTS = ["welcome", "what's new", "new features", "get started"]
WELCOME_BUTTONS = ["Continue", "Get started", "Next", "Got it", "OK", "Start"]

ERROR_TEXTS = [
    "we encountered a problem",
    "encountered a problem running",
    "problem running whatsapp",
    "something went wrong",
    "please reload",
]

MEMORY_TEXTS = [
    "memory full",
    "storage full",
    "no storage space",
    "not enough memory",
    "does not have enough space",
]

RELOAD_BUTTONS = ["Reload", "Refresh"]

POPUP_SELECTORS = [
    'div[role="dialog"]',
    'div[role="alert"]',
    'div[data-testid="modal"]',
    'div[data-testid="popup"]',
    'div[data-testid="alert"]',
    'div[data-testid="rate-limit-notification"]',
    'div[data-testid="error-notification"]',
]

SAFE_BUTTON_TEXTS = [
    "cancel",
    "dismiss",
    "not now",
    "later",
    "skip",
    "close",
    "ok",
    "got it",
    "continue",
    "next",
]

# Popup bodies are *classified*, never patched-up: a dialog that looks like
# it destroys data must not be clicked at all, and an unrecognised dialog is
# unknown and therefore also untouched. Only a body carrying positive safe
# markers may be reduced by a safe button.
POPUP_DANGEROUS_MARKERS = [
    "leave group",
    "leave community",
    "leave",
    "delete group",
    "delete account",
    "delete",
    "remove",
    "dismiss as admin",
    "remove as admin",
    "for everyone",
    "permanently",
    "discard",
    "confirm",
    "proceed",
    "yes",
]

POPUP_SAFE_MARKERS = [
    "what's new",
    "whats new",
    "welcome",
    "new features",
    "get started",
    "got it",
    "maybe later",
    "not now",
    "dismiss",
    "rate limit",
    "limit reached",
    "update available",
    "backup",
    "tip",
]


def classify_popup(text: str) -> str:
    """Classify a WhatsApp dialog body.

    Returns ``"dangerous"`` for anything that can hurt the account,
    ``"safe"`` for a positively-identified dismissable information card, and
    ``"unknown"`` otherwise. Both dangerous and unknown are left alone.
    """
    body = (text or "").lower()
    if any(marker in body for marker in POPUP_DANGEROUS_MARKERS):
        return "dangerous"
    if any(marker in body for marker in POPUP_SAFE_MARKERS):
        return "safe"
    return "unknown"


def popup_button_is_dangerous(label: str) -> bool:
    """True when a button label contains any destructive marker."""
    lower = (label or "").lower()
    return any(marker in lower for marker in POPUP_DANGEROUS_MARKERS)


def popup_button_is_safe(label: str) -> bool:
    """True only for positively known dismissive button labels."""
    lower = (label or "").strip().lower()
    if not lower:
        return False
    return any(safe in lower for safe in SAFE_BUTTON_TEXTS)


class WhatsAppBot:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.page = None
        self._pw = None
        self._browser = None
        self.is_connected = False
        self._failures = 0
        self._reconnect_attempts = 0
        # Set by the campaign runner so long waits can be aborted cooperatively.
        self.cancel_event = None

    def _cancelled(self) -> bool:
        return bool(self.cancel_event is not None and self.cancel_event.is_set())

    def cancelled(self) -> bool:
        return self._cancelled()

    # ── lifecycle ───────────────────────────────────────────────────────
    def start(self) -> None:
        if self._browser is not None:
            return
        update_connection_state("launching", "Launching WhatsApp Web browser")
        log("info", "[session] browser launch start", "poster")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-dev-shm-usage",
            ],
            viewport={"width": 1280, "height": 800},
        )
        self.page = self._browser.pages[0] if self._browser.pages else self._browser.new_page()
        try:
            self.page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
        except Exception:
            pass
        log("info", "[session] browser launch end", "poster")

    def stop(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None
        self.page = None
        self.is_connected = False
        update_connection_state("stopped", "WhatsApp browser stopped")

    def navigate(self, url: str = WHATSAPP_URL) -> None:
        if not self.page:
            self.start()
        update_connection_state("loading", "Loading WhatsApp Web")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            log("error", f"could not open WhatsApp Web: {exc}", "whatsapp")
            update_connection_state("error", f"Could not open WhatsApp Web: {exc}")
        log("info", f"[session] page loaded | url={getattr(self.page, 'url', url)}", "poster")

        self._wait_for_loading()
        self._wait_for_login(LOGIN_TIMEOUT)

    # ── headless / QR helpers ────────────────────────────────────────────
    def is_browser_closed(self) -> bool:
        """True when the Playwright context no longer has any open page."""
        context = self._browser
        if context is None:
            return True
        try:
            return len(context.pages) == 0
        except Exception:
            return True

    def capture_qr(self) -> Optional[bytes]:
        """Return PNG bytes of the QR region (or the page) when a QR is shown."""
        page = self.page
        if page is None:
            return None
        for selector in DISCONNECT_SELECTORS:
            if not selector.startswith("canvas") and "qr" not in selector:
                continue
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    return element.screenshot(type="png")
            except Exception:
                continue
        try:
            return page.screenshot(type="png")
        except Exception:
            return None

    def qr_data_url(self) -> Optional[str]:
        """Return the QR screenshot as a ``data:image/png;base64,…`` URL."""
        png = self.capture_qr()
        if not png:
            return None
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def switch_to_headed_for_qr(self) -> bool:
        """Stop a headless session and relaunch a visible one for scanning."""
        if not self.headless:
            return True
        try:
            self.stop()
        except Exception:
            pass
        self.headless = False
        try:
            self.start()
            if self.page is not None:
                try:
                    self.page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    log("warning", f"visible browser could not load WhatsApp: {exc}", "whatsapp")
                try:
                    self._wait_for_loading(timeout=30)
                except Exception:
                    pass
            update_connection_state(
                "waiting_qr",
                "Visible browser opened; scan the WhatsApp QR code",
                qr_visible=True,
            )
            return True
        except Exception as exc:
            log("error", f"could not open a visible WhatsApp browser: {exc}", "whatsapp")
            return False

    def relaunch_headless(self) -> bool:
        """Stop the visible browser and relaunch hidden, reusing the session."""
        try:
            self.stop()
        except Exception:
            pass
        self.headless = True
        try:
            self.start()
            if self.page is not None:
                try:
                    self.page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    log("warning", f"headless browser could not load WhatsApp: {exc}", "whatsapp")
                try:
                    self._wait_for_loading(timeout=30)
                except Exception:
                    pass
            return True
        except Exception as exc:
            log("error", f"could not relaunch WhatsApp headless: {exc}", "whatsapp")
            return False

    # ── public helpers ──────────────────────────────────────────────────
    def human_delay(self, low: Optional[float] = None, high: Optional[float] = None) -> None:
        if low is None:
            low = app_settings.get_float("post_min_delay", POST_MIN_DELAY)
        if high is None:
            high = app_settings.get_float("post_max_delay", POST_MAX_DELAY)
        if high < low:
            low, high = high, low
        time.sleep(random.uniform(low, high))

    def is_logged_in(self) -> bool:
        return self.check_connection()

    def is_definitely_disconnected(self) -> bool:
        """True only when a QR / phone-not-connected marker is visible.

        Unlike :meth:`check_connection`, an unknown page state is *not* a
        disconnect. Mid-operation code uses this so a transient selector miss
        cannot trigger a reload that wipes the current search.
        """
        if not self.page:
            return True
        try:
            return self._disconnected()
        except Exception:
            return False

    def check_connection(self) -> bool:
        """One non-destructive check of the current page state."""
        if not self.page:
            return False
        try:
            if self._disconnected():
                self.is_connected = False
                return False
            self.is_connected = self._connected()
            return self.is_connected
        except Exception:
            return False

    def ensure_connection(self, context: str = "operation") -> bool:
        """Verify WhatsApp is usable; recover through reloads / QR wait if not.

        A missing selector is not treated as a disconnect: the reference logic
        distinguishes connected / loading / disconnected / unknown states, and
        unknown is given a short grace period before any reload happens.
        """
        if self._cancelled():
            return False
        if self.check_connection():
            self._failures = 0
            update_connection_state("connected", "WhatsApp Web connected")
            return True

        self._failures += 1
        log("warning", f"WhatsApp not ready at '{context}' - checking state", "whatsapp")
        update_connection_state("disconnected", f"WhatsApp not ready at '{context}'")

        self._cancel_popups()

        # Loading: wait for the UI without reloading (reloads can loop forever).
        if self._loading():
            update_connection_state("loading", "WhatsApp Web is loading")
            deadline = time.time() + 90
            while time.time() < deadline:
                if self._cancelled():
                    return False
                if self._connected():
                    self.is_connected = True
                    self._failures = 0
                    update_connection_state("connected", "WhatsApp Web connected")
                    return True
                self._handle_error_popups()
                if self._disconnected():
                    break
                time.sleep(3)
            if self.check_connection():
                self._failures = 0
                update_connection_state("connected", "WhatsApp Web connected")
                return True

        if self._disconnected():
            if self._any_visible(DISCONNECT_SELECTORS):
                update_connection_state(
                    "waiting_qr",
                    "WhatsApp needs a QR scan: Linked devices > Link a device",
                    qr_visible=True,
                )
            return self._recover(context)

        # Unknown state: give WhatsApp a few seconds to settle before deciding.
        # It is deliberately NOT treated as a disconnect: a reload here wipes
        # an in-progress search and makes every later group appear missing.
        for _ in range(3):
            if self._cancelled():
                return False
            time.sleep(2)
            self._cancel_popups()
            if self.check_connection():
                self._failures = 0
                return True
            if self._disconnected():
                return self._recover(context)

        log(
            "warning",
            f"WhatsApp state unknown at '{context}'; assuming connected",
            "whatsapp",
        )
        self.is_connected = True
        self._failures = 0
        update_connection_state("connected", "WhatsApp Web connected (assumed)")
        return True

    # ── connection state ────────────────────────────────────────────────
    def _visible(self, selector: str) -> bool:
        try:
            element = self.page.query_selector(selector)
            return bool(element and element.is_visible())
        except Exception:
            return False

    def _any_visible(self, selectors: List[str]) -> bool:
        return any(self._visible(selector) for selector in selectors)

    def _connected(self) -> bool:
        return self._any_visible(CONNECTED_SELECTORS)

    def _disconnected(self) -> bool:
        if self._any_visible(DISCONNECT_SELECTORS):
            return True
        try:
            text = (self.page.inner_text("body") or "").lower()
            return any(marker in text for marker in DISCONNECT_TEXT)
        except Exception:
            return False

    def _loading(self) -> bool:
        if self._any_visible(LOADING_SELECTORS):
            return True
        try:
            text = (self.page.inner_text("body") or "").lower()
            return any(marker in text for marker in LOADING_TEXT)
        except Exception:
            return False

    # ── login / loading / recovery ──────────────────────────────────────
    def _wait_for_loading(self, timeout: int = 180) -> bool:
        update_connection_state("loading", "Waiting for WhatsApp Web to load")
        deadline = time.time() + timeout
        reloads = 0
        while time.time() < deadline:
            if self._cancelled():
                return False
            if self._connected():
                update_connection_state("connected", "WhatsApp Web connected")
                return True
            if self._disconnected():
                return True  # QR is visible - login loop handles it
            self._handle_error_popups()
            self._cancel_popups()
            if self._connected():
                return True
            if reloads < 3 and time.time() > deadline - timeout + 45:
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=60000)
                    reloads += 1
                    time.sleep(5)
                    continue
                except Exception:
                    reloads += 1
            time.sleep(2)
        return False

    def _wait_for_login(self, timeout: int = 300) -> bool:
        deadline = time.time() + timeout
        announced_qr = False
        last_progress = time.time()
        while time.time() < deadline:
            if self._cancelled():
                log("info", "login wait cancelled", "whatsapp")
                return False
            if self._connected():
                self.is_connected = True
                self._handle_welcome_popup()
                log("info", "WhatsApp Web connected", "whatsapp")
                log("info", "[session] login connected", "poster")
                update_connection_state("connected", "WhatsApp Web connected")
                return True

            self._handle_error_popups()
            self._cancel_popups(handle_welcome=False)

            if self._disconnected():
                update_connection_state(
                    "waiting_qr",
                    "Waiting for QR scan: WhatsApp > Linked devices > Link a device",
                    qr_visible=True,
                )
                if not announced_qr:
                    log(
                        "info",
                        "WhatsApp needs a scan: open WhatsApp > Linked devices > Link a device",
                        "whatsapp",
                    )
                    log("info", "[session] QR visible | waiting for scan", "poster")
                    announced_qr = True
            else:
                update_connection_state("waiting_login", "Waiting for WhatsApp Web login")

            if time.time() - last_progress > 30:
                last_progress = time.time()
                log("info", "still waiting for WhatsApp Web login", "whatsapp")
            time.sleep(2)

        log("error", f"WhatsApp login timed out after {timeout}s", "whatsapp")
        update_connection_state("error", f"WhatsApp login timed out after {timeout}s")
        return False

    def _recover(self, context: str) -> bool:
        deadline = time.time() + CONNECTION_WAIT_TIMEOUT
        attempt = 0
        max_attempts = max(1, int(CONNECTION_WAIT_TIMEOUT // 8))
        while time.time() < deadline:
            if self._cancelled():
                return False
            attempt += 1
            update_connection_state(
                "reconnecting",
                f"Recovering WhatsApp at '{context}'",
                attempt=attempt,
                max_attempts=max_attempts,
            )
            self._cancel_popups()
            try:
                self.page.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                log("warning", f"reload failed at '{context}': {exc}", "whatsapp")
            time.sleep(4)
            self._wait_for_loading(timeout=90)
            if self.check_connection():
                log("info", f"WhatsApp recovered at '{context}'", "whatsapp")
                self._failures = 0
                update_connection_state("connected", "WhatsApp recovered")
                return True
            if self._disconnected():
                log("warning", "WhatsApp shows a QR code - waiting for manual re-login", "whatsapp")
                update_connection_state(
                    "waiting_qr",
                    "WhatsApp shows a QR code - waiting for manual re-login",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    qr_visible=True,
                )
                if self._wait_for_login(timeout=max(60, int(deadline - time.time()))):
                    return True
                return False
            time.sleep(min(15, 3 * attempt))
        log("error", f"WhatsApp could not be recovered at '{context}'", "whatsapp")
        update_connection_state(
            "error",
            f"WhatsApp could not be recovered at '{context}'",
            attempt=attempt,
            max_attempts=max_attempts,
        )
        return False

    # ── popups ──────────────────────────────────────────────────────────
    def _handle_welcome_popup(self, timeout: int = 8) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for dialog in self.page.query_selector_all('div[role="dialog"], div[data-testid="modal"]'):
                    if not dialog.is_visible():
                        continue
                    text = (dialog.inner_text() or "").lower()
                    if not any(marker in text for marker in WELCOME_TEXTS):
                        continue
                    for button in dialog.query_selector_all("button, [role='button']"):
                        if not button.is_visible():
                            continue
                        label = (button.inner_text() or "").strip().lower()
                        if label in [b.lower() for b in WELCOME_BUTTONS]:
                            button.click()
                            time.sleep(1)
                            return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _handle_error_popups(self) -> bool:
        if not self.page:
            return False
        try:
            body = (self.page.inner_text("body") or "").lower()
        except Exception:
            return False

        for marker in MEMORY_TEXTS:
            if marker in body:
                self._click_text_button(["OK", "Ok"])
                log("error", "WhatsApp reports memory/disk full; free disk space", "whatsapp")
                return True

        for marker in ERROR_TEXTS:
            if marker in body:
                if not self._click_text_button(RELOAD_BUTTONS):
                    try:
                        self.page.reload(wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                time.sleep(3)
                return True
        return False

    def dismiss_popups(self, handle_welcome: bool = True) -> int:
        """Best-effort, classifier-gated popup dismissal.

        Public so the poster can call it at action boundaries instead of
        relying on Playwright's default dialog teardown.
        """
        return self._cancel_popups(handle_welcome=handle_welcome)

    def _cancel_popups(self, handle_welcome: bool = True) -> int:
        if not self.page:
            return 0
        if handle_welcome:
            self._handle_welcome_popup(timeout=2)
        handled = 0
        for selector in POPUP_SELECTORS:
            try:
                for popup in self.page.query_selector_all(selector):
                    if not popup.is_visible():
                        continue
                    text = (popup.inner_text() or "").lower()
                    kind = classify_popup(text)
                    if kind != "safe":
                        if kind == "dangerous":
                            log(
                                "info",
                                "dangerous WhatsApp popup detected; leaving it untouched",
                                "whatsapp",
                            )
                        continue
                    if self._click_popup_safe_button(popup):
                        handled += 1
                        time.sleep(0.4)
            except Exception:
                continue
        if handled:
            log("info", f"dismissed {handled} WhatsApp popup(s)", "whatsapp")
        return handled

    def _click_text_button(self, labels: List[str]) -> bool:
        for label in labels:
            try:
                button = self.page.query_selector(f'button:has-text("{label}")')
                if button and button.is_visible() and button.is_enabled():
                    button.click()
                    return True
            except Exception:
                continue
        return False

    def _click_popup_safe_button(self, popup) -> bool:
        try:
            for button in popup.query_selector_all("button, [role='button']"):
                if not button.is_visible() or not button.is_enabled():
                    continue
                label = (button.inner_text() or "").strip().lower()
                if not label:
                    continue
                if popup_button_is_dangerous(label):
                    # Never click destructive buttons, not even to “close”.
                    continue
                if popup_button_is_safe(label):
                    button.click()
                    return True
        except Exception:
            pass
        # Unknown/non-dismissable popups are deliberately left open.
        return False

    def get_stats(self) -> dict:
        return {
            "is_connected": self.is_connected,
            "consecutive_failures": self._failures,
        }
