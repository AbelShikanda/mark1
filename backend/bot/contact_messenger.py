from typing import List, Dict, Any

class ContactMessenger:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def send_message(self, contact: str, message: str) -> bool:
        try:
            search = self.bot.page.locator('[data-testid="chat-list-search"]')
            search.click()
            search.type(contact, delay=50)
            self.bot.page.click(f'text="{contact}"', timeout=5000)
            compose = self.bot.page.locator('[data-testid="conversation-compose-box-input"]')
            compose.click()
            compose.type(message, delay=100)
            self.bot.page.click('[data-testid="compose-btn-send"]', timeout=5000)
            self.bot.human_delay()
            return True
        except Exception as e:
            self.db.log("error", f"Failed to message {contact}: {e}", "contact_messenger")
            return False
