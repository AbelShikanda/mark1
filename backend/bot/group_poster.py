import time
from typing import List, Dict, Any

class GroupPoster:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def post_to_group(self, group_name: str, product: Dict[str, Any]) -> bool:
        try:
            self.bot.page.click(f'text="{group_name}"', timeout=5000)
            compose = self.bot.page.locator('[data-testid="conversation-compose-box-input"]')
            compose.click()
            text = f"*{product['name']}*\n{product.get('description','')}\n{product.get('link','')}"
            compose.type(text, delay=100)
            self.bot.page.click('[data-testid="compose-btn-send"]', timeout=5000)
            self.bot.human_delay()
            return True
        except Exception as e:
            self.db.log("error", f"Failed to post to {group_name}: {e}", "group_poster")
            return False
