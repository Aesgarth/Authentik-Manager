import httpx
from typing import Dict, Any, Optional
from app.config import settings

class WhatsAppService:
    def __init__(self):
        self.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")
        self.enabled = settings.WHATSAPP_ENABLED

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
                res = await client.get(f"{self.base_url}/status")
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
                json={"recipient": recipient, "message": message},
            )
            if res.status_code != 200:
                err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = err_data.get("error") or res.text or "Failed to send WhatsApp message"
                raise RuntimeError(error_msg)
            return res.json()

    async def logout(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(f"{self.base_url}/logout")
            return res.json()

whatsapp_service = WhatsAppService()
