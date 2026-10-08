import httpx
from typing import Dict, Any, Optional
from app.config import settings

from urllib.parse import urlsplit

class WhatsAppService:
    def __init__(self):
        self.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")
        self.enabled = settings.WHATSAPP_ENABLED
        self._initial_origin = self._extract_origin(self.base_url)

    @staticmethod
    def _extract_origin(url: str) -> str:
        try:
            return urlsplit(url).netloc
        except Exception:
            return ""

    def _get_headers(self) -> Dict[str, str]:
        # Defense in depth: only attach internal bridge secret to the configured bridge origin
        current_origin = self._extract_origin(self.base_url)
        if current_origin and current_origin == self._initial_origin:
            secret = settings.INTERNAL_SERVICE_SECRET or ""
            return {"X-Bridge-Secret": secret}
        return {}

    async def get_status(self) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "status": "disabled",
                "phone": None,
                "qrCodeDataUrl": None,
                "lastConnected": None,
                "available": False,
            }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/status", headers=self._get_headers())
                if res.status_code == 200:
                    data = res.json()
                    data["available"] = True
                    return data
        except Exception:
            pass

        return {
            "status": "service_offline",
            "phone": None,
            "qrCodeDataUrl": None,
            "lastConnected": None,
            "available": False,
        }

    async def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        if not self.enabled:
            raise ValueError("WhatsApp integration is disabled in configuration.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{self.base_url}/send",
                headers=self._get_headers(),
                json={"recipient": recipient, "message": message},
            )
            if res.status_code != 200:
                err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = err_data.get("error") or res.text or "Failed to send WhatsApp message"
                raise RuntimeError(error_msg)
            return res.json()

    async def logout(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(f"{self.base_url}/logout", headers=self._get_headers())
            return res.json()

whatsapp_service = WhatsAppService()
