import base64
import hashlib
import logging
import httpx
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from app.config import settings
from app.database import get_all_app_settings, set_app_setting
from app.models import SettingsResponse, UpdateSettingsRequest, TestConnectionRequest, TestConnectionResponse
from app.services.audit_service import audit_service

logger = logging.getLogger("authentik_manager.settings_service")

class SettingsService:
    def __init__(self):
        # Derive a 32-byte Fernet key from SECRET_KEY
        key_digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_digest))
        self._custom_invite_message: Optional[str] = None
        self._notification_webhook_url: Optional[str] = None
        self._default_lease_duration_hours: int = 72
        self._default_invite_expiry_days: int = 7

    def encrypt_secret(self, raw: str) -> str:
        if not raw:
            return ""
        return self._fernet.encrypt(raw.encode("utf-8")).decode("utf-8")

    def decrypt_secret(self, encrypted: str) -> str:
        if not encrypted:
            return ""
        try:
            return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to decrypt stored secret: {e}")
            return ""

    async def load_settings_into_runtime(self):
        """Loads persistent database settings overrides and applies them to runtime config."""
        try:
            all_settings = await get_all_app_settings()
            for key, item in all_settings.items():
                val = item.get("value", "")
                is_secret = bool(item.get("is_secret", 0))
                if is_secret:
                    val = self.decrypt_secret(val)

                if key == "authentik_url" and val:
                    settings.AUTHENTIK_URL = val
                elif key == "authentik_token" and val:
                    settings.AUTHENTIK_TOKEN = val
                elif key == "authentik_insecure_skip_verify":
                    settings.AUTHENTIK_INSECURE_SKIP_VERIFY = (val.lower() in ("true", "1", "yes"))
                elif key == "app_group_prefix" and val:
                    settings.APP_GROUP_PREFIX = val
                elif key == "default_enrollment_flow" and val:
                    settings.DEFAULT_ENROLLMENT_FLOW = val
                elif key == "whatsapp_enabled":
                    settings.WHATSAPP_ENABLED = (val.lower() in ("true", "1", "yes"))
                elif key == "whatsapp_service_url" and val:
                    settings.WHATSAPP_SERVICE_URL = val
                elif key == "default_country_code" and val:
                    settings.DEFAULT_COUNTRY_CODE = val
                elif key == "custom_invite_message":
                    self._custom_invite_message = val
                elif key == "notification_webhook_url":
                    self._notification_webhook_url = val
                elif key == "default_lease_duration_hours" and val:
                    try:
                        self._default_lease_duration_hours = int(val)
                    except ValueError:
                        pass
                elif key == "default_invite_expiry_days" and val:
                    try:
                        self._default_invite_expiry_days = int(val)
                    except ValueError:
                        pass

            # Sync whatsapp_service instance
            from app.services.whatsapp_service import whatsapp_service
            whatsapp_service.enabled = settings.WHATSAPP_ENABLED
            whatsapp_service.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")

            logger.info("Successfully loaded system settings from local database.")
        except Exception as e:
            logger.error(f"Error loading system settings: {e}")

    def _mask_token(self, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 8:
            return "••••••••"
        return f"••••••••{token[-4:]}"

    async def get_settings_response(self) -> SettingsResponse:
        token = settings.AUTHENTIK_TOKEN
        token_configured = bool(token and token != "your_authentik_api_bearer_token_here")
        return SettingsResponse(
            authentik_url=settings.AUTHENTIK_URL,
            authentik_token_masked=self._mask_token(token) if token_configured else "",
            authentik_token_configured=token_configured,
            authentik_insecure_skip_verify=settings.AUTHENTIK_INSECURE_SKIP_VERIFY,
            app_group_prefix=settings.APP_GROUP_PREFIX,
            default_enrollment_flow=settings.DEFAULT_ENROLLMENT_FLOW,
            whatsapp_enabled=settings.WHATSAPP_ENABLED,
            whatsapp_service_url=settings.WHATSAPP_SERVICE_URL,
            default_country_code=settings.DEFAULT_COUNTRY_CODE,
            custom_invite_message=self._custom_invite_message,
            notification_webhook_url=self._notification_webhook_url,
            default_lease_duration_hours=self._default_lease_duration_hours,
            default_invite_expiry_days=self._default_invite_expiry_days,
        )

    async def update_settings(self, req: UpdateSettingsRequest, actor: str = "Admin") -> SettingsResponse:
        updated_keys = []

        if req.authentik_url is not None:
            clean_url = req.authentik_url.strip().rstrip("/")
            await set_app_setting("authentik_url", clean_url)
            settings.AUTHENTIK_URL = clean_url
            updated_keys.append("authentik_url")

        if req.authentik_token is not None:
            clean_token = req.authentik_token.strip()
            # Only update if user provided a new unmasked token
            if clean_token and not clean_token.startswith("••"):
                encrypted = self.encrypt_secret(clean_token)
                await set_app_setting("authentik_token", encrypted, is_secret=True)
                settings.AUTHENTIK_TOKEN = clean_token
                updated_keys.append("authentik_token")

        if req.authentik_insecure_skip_verify is not None:
            await set_app_setting("authentik_insecure_skip_verify", str(req.authentik_insecure_skip_verify).lower())
            settings.AUTHENTIK_INSECURE_SKIP_VERIFY = req.authentik_insecure_skip_verify
            updated_keys.append("authentik_insecure_skip_verify")

        if req.app_group_prefix is not None:
            await set_app_setting("app_group_prefix", req.app_group_prefix)
            settings.APP_GROUP_PREFIX = req.app_group_prefix
            updated_keys.append("app_group_prefix")

        if req.default_enrollment_flow is not None:
            await set_app_setting("default_enrollment_flow", req.default_enrollment_flow.strip())
            settings.DEFAULT_ENROLLMENT_FLOW = req.default_enrollment_flow.strip()
            updated_keys.append("default_enrollment_flow")

        if req.whatsapp_enabled is not None:
            await set_app_setting("whatsapp_enabled", str(req.whatsapp_enabled).lower())
            settings.WHATSAPP_ENABLED = req.whatsapp_enabled
            updated_keys.append("whatsapp_enabled")

        if req.whatsapp_service_url is not None:
            clean_wa = req.whatsapp_service_url.strip().rstrip("/")
            await set_app_setting("whatsapp_service_url", clean_wa)
            settings.WHATSAPP_SERVICE_URL = clean_wa
            updated_keys.append("whatsapp_service_url")

        if req.default_country_code is not None:
            await set_app_setting("default_country_code", req.default_country_code.strip())
            settings.DEFAULT_COUNTRY_CODE = req.default_country_code.strip()
            updated_keys.append("default_country_code")

        if req.custom_invite_message is not None:
            await set_app_setting("custom_invite_message", req.custom_invite_message)
            self._custom_invite_message = req.custom_invite_message
            updated_keys.append("custom_invite_message")

        if req.notification_webhook_url is not None:
            await set_app_setting("notification_webhook_url", req.notification_webhook_url.strip())
            self._notification_webhook_url = req.notification_webhook_url.strip()
            updated_keys.append("notification_webhook_url")

        if req.default_lease_duration_hours is not None:
            await set_app_setting("default_lease_duration_hours", str(req.default_lease_duration_hours))
            self._default_lease_duration_hours = req.default_lease_duration_hours
            updated_keys.append("default_lease_duration_hours")

        if req.default_invite_expiry_days is not None:
            await set_app_setting("default_invite_expiry_days", str(req.default_invite_expiry_days))
            self._default_invite_expiry_days = req.default_invite_expiry_days
            updated_keys.append("default_invite_expiry_days")

        # Sync services
        from app.services.whatsapp_service import whatsapp_service
        whatsapp_service.enabled = settings.WHATSAPP_ENABLED
        whatsapp_service.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")

        await audit_service.log(
            actor=actor,
            action="UPDATE_SYSTEM_SETTINGS",
            target_type="SYSTEM_CONFIG",
            target_name="System Settings",
            target_id="settings",
            details=f"Updated keys: {', '.join(updated_keys)}",
            status="SUCCESS"
        )

        return await self.get_settings_response()

    async def test_authentik_connection(self, req: TestConnectionRequest) -> TestConnectionResponse:
        url = (req.url or settings.AUTHENTIK_URL).strip().rstrip("/")
        token = req.token or settings.AUTHENTIK_TOKEN
        # If the user passed masked token, fallback to current settings.AUTHENTIK_TOKEN
        if token and token.startswith("••"):
            token = settings.AUTHENTIK_TOKEN

        insecure = req.insecure_skip_verify if req.insecure_skip_verify is not None else settings.AUTHENTIK_INSECURE_SKIP_VERIFY
        verify_ssl = not insecure

        if not token or token == "your_authentik_api_bearer_token_here":
            return TestConnectionResponse(
                success=False,
                error="No Authentik API token configured. Please enter a valid Bearer token."
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        test_endpoint = f"{url}/api/v3/core/applications/?page_size=1"
        try:
            async with httpx.AsyncClient(verify=verify_ssl, timeout=8.0) as client:
                res = await client.get(test_endpoint, headers=headers)
                if res.status_code == 200:
                    return TestConnectionResponse(success=True)
                elif res.status_code in (401, 403):
                    return TestConnectionResponse(
                        success=False,
                        error=f"Authentication failed (HTTP {res.status_code}): Ensure your Authentik token has sufficient permissions."
                    )
                else:
                    return TestConnectionResponse(
                        success=False,
                        error=f"Authentik returned HTTP {res.status_code}: {res.text[:200]}"
                    )
        except httpx.ConnectError:
            return TestConnectionResponse(
                success=False,
                error=f"Unable to reach host at {url}. Check hostname, port, and network reachability."
            )
        except httpx.ConnectTimeout:
            return TestConnectionResponse(
                success=False,
                error=f"Connection timed out reaching {url}."
            )
        except Exception as e:
            return TestConnectionResponse(
                success=False,
                error=f"Connection test failed: {str(e)}"
            )

settings_service = SettingsService()
