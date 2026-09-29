import logging
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger("authentik_manager.notification_service")

class NotificationService:
    def __init__(self):
        self.ntfy_topic: Optional[str] = None
        self.ntfy_server_url: str = "https://ntfy.sh"
        self.webhook_url: Optional[str] = None

    def configure(
        self,
        ntfy_topic: Optional[str] = None,
        ntfy_server_url: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        self.ntfy_topic = ntfy_topic.strip() if ntfy_topic else None
        if ntfy_server_url and ntfy_server_url.strip():
            self.ntfy_server_url = ntfy_server_url.strip().rstrip("/")
        else:
            self.ntfy_server_url = "https://ntfy.sh"
        self.webhook_url = webhook_url.strip() if webhook_url else None

    async def send_notification(
        self,
        title: str,
        message: str,
        tags: Optional[List[str]] = None,
        priority: str = "default",
        action_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches notification to all configured channels (NTFY, Discord, Webhook)."""
        results: Dict[str, Any] = {}

        # 1. NTFY Push Notification
        if self.ntfy_topic:
            ntfy_url = f"{self.ntfy_server_url}/{self.ntfy_topic}"
            headers = {
                "Title": title,
                "Priority": priority,
            }
            if tags:
                headers["Tags"] = ",".join(tags)
            if action_url:
                headers["Click"] = action_url

            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    res = await client.post(ntfy_url, content=message.encode("utf-8"), headers=headers)
                    results["ntfy"] = {"success": res.status_code == 200, "status_code": res.status_code}
            except Exception as e:
                logger.warning(f"Failed to dispatch NTFY push notification: {e}")
                results["ntfy"] = {"success": False, "error": str(e)}

        # 2. Webhook (Discord or Generic JSON)
        if self.webhook_url:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    if "discord.com/api/webhooks" in self.webhook_url:
                        # Discord Embed format
                        discord_color = 0xFD7E14 # Authentik Orange default
                        if any(t in ("tada", "check", "party") for t in (tags or [])):
                            discord_color = 0x10B981 # Emerald Green
                        elif any(t in ("clock", "alarm", "warning") for t in (tags or [])):
                            discord_color = 0xF59E0B # Amber
                        elif any(t in ("skull", "rotating_light", "alert") for t in (tags or [])):
                            discord_color = 0xEF4444 # Rose Red

                        payload = {
                            "username": "Authentik Access Manager",
                            "avatar_url": "https://goauthentik.io/img/icon.png",
                            "embeds": [
                                {
                                    "title": title,
                                    "description": message,
                                    "color": discord_color,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "footer": {"text": "Authentik Access Manager"},
                                    **({"url": action_url} if action_url else {})
                                }
                            ]
                        }
                        res = await client.post(self.webhook_url, json=payload)
                    else:
                        # Generic JSON Webhook format
                        payload = {
                            "event": "authentik_manager_alert",
                            "title": title,
                            "message": message,
                            "tags": tags or [],
                            "priority": priority,
                            "action_url": action_url,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        res = await client.post(self.webhook_url, json=payload)

                    results["webhook"] = {"success": res.status_code in (200, 204), "status_code": res.status_code}
            except Exception as e:
                logger.warning(f"Failed to dispatch webhook notification: {e}")
                results["webhook"] = {"success": False, "error": str(e)}

        return results

    async def notify_invite_redeemed(self, user_name: str, user_email: Optional[str], assigned_apps: List[str]):
        apps_str = ", ".join(assigned_apps) if assigned_apps else "default services"
        title = f"🎉 New Member Joined: {user_name}"
        email_part = f" ({user_email})" if user_email else ""
        message = f"{user_name}{email_part} has redeemed their invite and gained access to: {apps_str}."
        await self.send_notification(
            title=title,
            message=message,
            tags=["tada", "authentik"],
            priority="default"
        )

    async def notify_lease_expired(self, user_name: str, app_name: str, role: str):
        title = f"⏱️ Guest Pass Expired: {user_name}"
        message = f"Temporary {role.upper()} access for {user_name} on {app_name} has expired and was automatically revoked in Authentik."
        await self.send_notification(
            title=title,
            message=message,
            tags=["clock", "lock"],
            priority="default"
        )

    async def notify_unsecured_app_detected(self, app_name: str):
        title = f"⚠️ Unsecured Service Detected: {app_name}"
        message = f"Application '{app_name}' does not have any policy bindings or protecting groups attached. It is open to all users."
        await self.send_notification(
            title=title,
            message=message,
            tags=["warning", "shield"],
            priority="high"
        )

notification_service = NotificationService()
