from playwright.sync_api import sync_playwright
from config import SESSION_DIR, POST_MIN_DELAY, POST_MAX_DELAY
import random
import time

class WhatsAppBot:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.page = None
        self._pw = None
        self._browser = None

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self._browser.pages[0] if self._browser.pages else self._browser.new_page()

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

    def navigate(self, url: str = "https://web.whatsapp.com") -> None:
        if not self.page:
            self.start()
        self.page.goto(url, wait_until="networkidle")

    def is_logged_in(self) -> bool:
        if not self.page:
            return False
        try:
            return self.page.locator('[data-testid="chat-list"]') \
                .locator('[role="gridcell"]', has_text="New chat").count() > 0 \
                or self.page.locator('div[data-testid="chat-list"]').count() > 0
        except Exception:
            return False

    def human_delay(self) -> None:
        time.sleep(random.uniform(POST_MIN_DELAY, POST_MAX_DELAY))
