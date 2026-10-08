import asyncio
import logging
import httpx
from typing import Optional, List, Dict, Any
from app.models import TestTelegramResponse

logger = logging.getLogger("authentik_manager.telegram_service")

class TelegramService:
    def __init__(self):
        self.enabled: bool = False
        self.bot_token: Optional[str] = None
        self.admin_chat_ids: List[str] = []
        self._poll_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._last_update_id: int = 0

    def configure(
        self,
        enabled: bool = False,
        bot_token: Optional[str] = None,
        admin_chat_ids: Optional[str] = None,
    ):
        """Updates Telegram service runtime credentials and adjusts polling worker."""
        old_token = self.bot_token
        old_enabled = self.enabled

        self.enabled = enabled
        self.bot_token = bot_token.strip() if bot_token else None

        if admin_chat_ids:
            self.admin_chat_ids = [c.strip() for c in admin_chat_ids.split(",") if c.strip()]
        else:
            self.admin_chat_ids = []

        # If token or enabled status changed while running, restart polling
        if self._running:
            if not self.enabled or not self.bot_token:
                asyncio.create_task(self.stop_polling())
            elif old_token != self.bot_token or not old_enabled:
                asyncio.create_task(self._restart_polling())
        elif self.enabled and self.bot_token:
            asyncio.create_task(self.start_polling())

    def is_admin_chat(self, chat_id: str) -> bool:
        if not self.admin_chat_ids:
            return False
        clean_id = str(chat_id).strip()
        # Wildcards are rejected for security; exact chat ID required
        if clean_id == "*":
            return False
        return clean_id in self.admin_chat_ids

    async def test_connection(self, token: Optional[str] = None) -> TestTelegramResponse:
        active_token = (token or self.bot_token or "").strip()
        if not active_token:
            return TestTelegramResponse(
                success=False,
                error="No Telegram Bot token provided. Please enter a valid bot token from @BotFather."
            )

        url = f"https://api.telegram.org/bot{active_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                data = res.json()
                if res.status_code == 200 and data.get("ok"):
                    result = data.get("result", {})
                    return TestTelegramResponse(
                        success=True,
                        bot_username=result.get("username"),
                        first_name=result.get("first_name")
                    )
                else:
                    err_desc = data.get("description", f"HTTP {res.status_code}")
                    return TestTelegramResponse(success=False, error=err_desc)
        except Exception as e:
            logger.error(f"Telegram connection test error: {e}")
            return TestTelegramResponse(success=False, error=str(e))

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = True
    ) -> bool:
        if not self.bot_token:
            logger.warning("Attempted to send Telegram message without configured bot token.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return True
                logger.warning(f"Telegram sendMessage failed (status {res.status_code}): {res.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to dispatch Telegram message to {chat_id}: {e}")
            return False

    async def broadcast_admin(self, text: str, parse_mode: str = "Markdown") -> int:
        """Sends a message to all configured admin chat IDs."""
        if not self.enabled or not self.bot_token or not self.admin_chat_ids:
            return 0

        sent_count = 0
        for cid in self.admin_chat_ids:
            if cid == "*":
                continue
            ok = await self.send_message(chat_id=cid, text=text, parse_mode=parse_mode)
            if ok:
                sent_count += 1
        return sent_count

    async def start_polling(self):
        """Starts the long polling loop for incoming Telegram bot commands."""
        if self._running or not self.enabled or not self.bot_token:
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram Bot long polling started.")

    async def stop_polling(self):
        """Stops the long polling loop cleanly."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("Telegram Bot polling stopped.")

    async def _restart_polling(self):
        await self.stop_polling()
        await self.start_polling()

    async def _poll_loop(self):
        from app.services.bot_service import bot_service

        logger.info("Entering Telegram update polling loop...")
        backoff = 2

        while self._running:
            if not self.bot_token:
                await asyncio.sleep(5)
                continue

            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "timeout": 20,
                "allowed_updates": '["message"]'
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.get(url, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        backoff = 2 # Reset backoff on success
                        if data.get("ok"):
                            for update in data.get("result", []):
                                self._last_update_id = update["update_id"]
                                msg = update.get("message")
                                if not msg or "text" not in msg:
                                    continue

                                chat_id = str(msg["chat"]["id"])
                                text = msg["text"].strip()

                                # Validate admin authorization
                                if self.is_admin_chat(chat_id):
                                    reply = await bot_service.process_message(
                                        sender=f"tg_{chat_id}",
                                        raw_message=text,
                                        channel="telegram"
                                    )
                                    if reply:
                                        await self.send_message(chat_id=chat_id, text=reply)
                                else:
                                    # Inform sender of their chat_id for easy setup
                                    unauth_msg = (
                                        "⛔ *Unauthorized*\n\n"
                                        f"Your Telegram Chat ID is: `{chat_id}`\n\n"
                                        "To authorize this chat to manage Authentik, add this ID in the Authentik Manager web dashboard:\n"
                                        "👉 *Admin & Settings > Telegram Admin Chat IDs*"
                                    )
                                    await self.send_message(chat_id=chat_id, text=unauth_msg)
                    elif res.status_code == 409:
                        # Conflict: Another instance or webhook is active
                        logger.warning("Telegram 409 Conflict: Another polling instance is active. Retrying in 10s...")
                        await asyncio.sleep(10)
                    else:
                        logger.warning(f"Telegram getUpdates returned HTTP {res.status_code}")
                        await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}. Backing off {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

telegram_service = TelegramService()
