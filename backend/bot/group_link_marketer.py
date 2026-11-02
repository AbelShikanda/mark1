from typing import List, Dict, Any

class GroupLinkMarketer:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def send_link(self, group_name: str, link: str, message: Optional[str] = None) -> bool:
        try:
            self.bot.page.click(f'text="{group_name}"', timeout=5000)
            compose = self.bot.page.locator('[data-testid="conversation-compose-box-input"]')
            compose.click()
            text = message or ""
            if link:
                text = f"{text}\n{link}" if text else link
            compose.type(text, delay=100)
            self.bot.page.click('[data-testid="compose-btn-send"]', timeout=5000)
            self.bot.human_delay()
            return True
        except Exception as e:
            self.db.log("error", f"Failed link to {group_name}: {e}", "group_link_marketer")
            return False
