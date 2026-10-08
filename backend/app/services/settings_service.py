import os
import base64
import hashlib
import logging
import secrets
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from cryptography.fernet import Fernet
from app.config import settings
from app.database import get_all_app_settings, set_app_setting
from app.authentik_client import authentik_client
from app.models import (
    SettingsResponse,
    UpdateSettingsRequest,
    TestConnectionRequest,
    TestConnectionResponse,
    TestTelegramRequest,
    TestTelegramResponse,
    AutoSetupOidcRequest,
    AutoSetupOidcResponse,
)
from app.security import hash_password, verify_password, validate_external_url, is_insecure_password
from app.services.audit_service import audit_service

logger = logging.getLogger("authentik_manager.settings_service")

class SettingsService:
    def __init__(self):
        # Derive a 32-byte Fernet key from SECRET_KEY
        key_digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_digest))

        # Setup fallback Fernets for seamless secret decryption during SECRET_KEY rotation
        self._fallback_fernets: List[Fernet] = []
        for legacy_key in [
            "changeme-in-production-use-a-strong-secret-key-32chars",
            "change-this-to-a-random-32-character-secret-key",
        ]:
            if legacy_key != settings.SECRET_KEY:
                leg_digest = hashlib.sha256(legacy_key.encode()).digest()
                self._fallback_fernets.append(Fernet(base64.urlsafe_b64encode(leg_digest)))

        self._app_url: Optional[str] = None
        self._custom_invite_message: Optional[str] = None
        self._notification_webhook_url: Optional[str] = None
        self._ntfy_topic: Optional[str] = None
        self._ntfy_server_url: str = "https://ntfy.sh"
        self._admin_phone_numbers: Optional[str] = None
        self._telegram_enabled: bool = False
        self._telegram_bot_token: Optional[str] = None
        self._telegram_admin_chat_ids: Optional[str] = None
        self._default_lease_duration_hours: int = 72
        self._default_invite_expiry_days: int = 7
        self._webhook_secret: Optional[str] = None
        self._admin_password_hash: Optional[str] = None

    def verify_admin_password(self, candidate: str) -> bool:
        """Constant-time verification of candidate against hashed or configured admin password."""
        if not candidate:
            return False
        if self._admin_password_hash:
            return verify_password(candidate, self._admin_password_hash)
        if is_insecure_password(settings.ADMIN_PASSWORD):
            return False
        if settings.ADMIN_PASSWORD:
            return verify_password(candidate, settings.ADMIN_PASSWORD)
        return False

    def is_password_configured(self) -> bool:
        if self._admin_password_hash:
            return True
        return bool(settings.ADMIN_PASSWORD and not is_insecure_password(settings.ADMIN_PASSWORD))

    def encrypt_secret(self, raw: str) -> str:
        if not raw:
            return ""
        return self._fernet.encrypt(raw.encode("utf-8")).decode("utf-8")

    def decrypt_secret(self, encrypted: str, key_name: str = "") -> tuple[str, bool]:
        """
        Decrypts stored ciphertext. If encrypted with a legacy default key,
        decrypts successfully and signals that re-encryption is needed.
        """
        if not encrypted:
            return "", False
        try:
            return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8"), False
        except Exception:
            pass

        # Try fallback decryptors
        for fb in self._fallback_fernets:
            try:
                decrypted = fb.decrypt(encrypted.encode("utf-8")).decode("utf-8")
                return decrypted, True
            except Exception:
                continue

        logger.warning(f"Failed to decrypt stored secret for key '{key_name}'.")
        return "", False

    async def load_settings_into_runtime(self):
        """Loads persistent database settings overrides and applies them to runtime config."""
        try:
            all_settings = await get_all_app_settings()
            for key, item in all_settings.items():
                val = item.get("value", "")
                is_secret = bool(item.get("is_secret", 0))
                if is_secret:
                    if key in ("admin_password_hash", "admin_password"):
                        pass
                    else:
                        val, needs_reencrypt = self.decrypt_secret(val, key_name=key)
                        if needs_reencrypt and val:
                            new_cipher = self.encrypt_secret(val)
                            await set_app_setting(key, new_cipher, is_secret=True)
                            logger.info(f"Automatically re-encrypted stored secret '{key}' with active SECRET_KEY.")

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
                elif key == "ntfy_topic":
                    self._ntfy_topic = val
                elif key == "ntfy_server_url" and val:
                    self._ntfy_server_url = val
                elif key == "admin_phone_numbers":
                    self._admin_phone_numbers = val
                elif key == "telegram_enabled":
                    self._telegram_enabled = (val.lower() in ("true", "1", "yes"))
                elif key == "telegram_bot_token" and val:
                    self._telegram_bot_token = val
                elif key == "telegram_admin_chat_ids":
                    self._telegram_admin_chat_ids = val
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
                elif key == "auth_method" and val:
                    settings.AUTH_METHOD = val
                elif key == "admin_password_hash" and val:
                    self._admin_password_hash = val
                elif key == "admin_password" and val:
                    if not self._admin_password_hash and not is_insecure_password(val):
                        self._admin_password_hash = hash_password(val)
                    settings.ADMIN_PASSWORD = val
                elif key == "webhook_secret":
                    self._webhook_secret = val if val else None
                    settings.WEBHOOK_SECRET = val if val else None
                elif key == "app_url" and val:
                    self._app_url = val
                elif key == "oidc_client_id" and val:
                    settings.OIDC_CLIENT_ID = val
                elif key == "oidc_client_secret" and val:
                    settings.OIDC_CLIENT_SECRET = val
                elif key == "oidc_issuer_url" and val:
                    settings.OIDC_ISSUER_URL = val
                elif key == "oidc_redirect_uri" and val:
                    settings.OIDC_REDIRECT_URI = val
                elif key == "oidc_admin_group" and val:
                    settings.OIDC_ADMIN_GROUP = val

            # If no admin password hash is configured, generate or save one
            if not self._admin_password_hash:
                configured_pw = (settings.ADMIN_PASSWORD or "").strip()
                if is_insecure_password(configured_pw):
                    one_time_pw = secrets.token_urlsafe(16)
                    hashed = hash_password(one_time_pw)
                    await set_app_setting("admin_password_hash", hashed, is_secret=True)
                    self._admin_password_hash = hashed
                    settings.ADMIN_PASSWORD = one_time_pw

                    data_dir = os.path.dirname(settings.SQLITE_DB_PATH) or "data"
                    pw_file = os.path.join(data_dir, ".initial_admin_password")
                    try:
                        os.makedirs(data_dir, exist_ok=True)
                        with open(pw_file, "w", encoding="utf-8") as f:
                            f.write(one_time_pw)
                        if hasattr(os, "chmod"):
                            try:
                                os.chmod(pw_file, 0o600)
                            except Exception:
                                pass
                        logger.warning(
                            "\n" + "=" * 65 + "\n"
                            + "SECURITY NOTICE: No custom ADMIN_PASSWORD was configured in environment.\n"
                            + "A secure random one-time administrator password has been generated:\n"
                            + f"    PASSWORD: {one_time_pw}\n"
                            + f"Saved to: {pw_file}\n"
                            + "Please sign in and change your administrator password in Settings.\n"
                            + "=" * 65
                        )
                    except Exception as e:
                        logger.warning(f"Could not persist initial admin password: {e}")
                else:
                    hashed = hash_password(configured_pw)
                    await set_app_setting("admin_password_hash", hashed, is_secret=True)
                    self._admin_password_hash = hashed

            # Sync whatsapp_service instance
            from app.services.whatsapp_service import whatsapp_service
            whatsapp_service.enabled = settings.WHATSAPP_ENABLED
            whatsapp_service.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")

            # Sync notification_service instance
            from app.services.notification_service import notification_service
            notification_service.configure(
                ntfy_topic=self._ntfy_topic,
                ntfy_server_url=self._ntfy_server_url,
                webhook_url=self._notification_webhook_url
            )

            # Sync telegram_service instance
            from app.services.telegram_service import telegram_service
            telegram_service.configure(
                enabled=self._telegram_enabled,
                bot_token=self._telegram_bot_token,
                admin_chat_ids=self._telegram_admin_chat_ids
            )

            logger.info("Successfully loaded system settings from local database.")
        except Exception as e:
            logger.error(f"Error loading system settings: {e}")

    def _mask_token(self, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 8:
            return "••••••••"
        return f"••••••••{token[-4:]}"

    def get_webhook_secret(self) -> Optional[str]:
        return self._webhook_secret or getattr(settings, "WEBHOOK_SECRET", None)

    async def get_settings_response(self) -> SettingsResponse:
        token = settings.AUTHENTIK_TOKEN
        token_configured = bool(token and token != "your_authentik_api_bearer_token_here")
        webhook_sec = self.get_webhook_secret()
        webhook_secret_configured = bool(webhook_sec)
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
            ntfy_topic=self._ntfy_topic,
            ntfy_server_url=self._ntfy_server_url,
            admin_phone_numbers=self._admin_phone_numbers,
            telegram_enabled=self._telegram_enabled,
            telegram_bot_token_masked=self._mask_token(self._telegram_bot_token) if self._telegram_bot_token else "",
            telegram_bot_token_configured=bool(self._telegram_bot_token),
            telegram_admin_chat_ids=self._telegram_admin_chat_ids,
            default_lease_duration_hours=self._default_lease_duration_hours,
            default_invite_expiry_days=self._default_invite_expiry_days,
            # OIDC & Security
            auth_method=settings.AUTH_METHOD,
            admin_password_configured=self.is_password_configured(),
            webhook_secret_configured=webhook_secret_configured,
            webhook_secret_masked=self._mask_token(webhook_sec) if webhook_secret_configured else "",
            app_url=self._app_url,
            oidc_client_id=settings.OIDC_CLIENT_ID or "",
            oidc_client_secret_masked=self._mask_token(settings.OIDC_CLIENT_SECRET) if settings.OIDC_CLIENT_SECRET else "",
            oidc_client_secret_configured=bool(settings.OIDC_CLIENT_SECRET),
            oidc_issuer_url=settings.OIDC_ISSUER_URL or "",
            oidc_redirect_uri=settings.OIDC_REDIRECT_URI or "",
            oidc_admin_group=settings.OIDC_ADMIN_GROUP or "authentik Admins",
            oidc_configured=bool(settings.OIDC_CLIENT_ID and settings.OIDC_ISSUER_URL),
        )

    async def update_settings(self, req: UpdateSettingsRequest, actor: str = "Admin") -> SettingsResponse:
        updated_keys = []

        # Check if sensitive security parameters are being changed
        is_security_change = (
            req.admin_password is not None
            or req.auth_method is not None
            or req.authentik_url is not None
            or (req.authentik_token is not None and not req.authentik_token.startswith("••"))
        )

        if is_security_change and self.is_password_configured() and settings.AUTH_METHOD == "password":
            if not req.current_password or not self.verify_admin_password(req.current_password):
                raise HTTPException(
                    status_code=403,
                    detail="Current administrator password is required to change security credentials or authentication method."
                )

        if req.authentik_url is not None:
            clean_url = req.authentik_url.strip().rstrip("/")
            valid, err = validate_external_url(clean_url)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Invalid authentik_url: {err}")
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
            valid, err = validate_external_url(clean_wa)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Invalid whatsapp_service_url: {err}")
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
            clean_nw = req.notification_webhook_url.strip()
            if clean_nw:
                valid, err = validate_external_url(clean_nw)
                if not valid:
                    raise HTTPException(status_code=400, detail=f"Invalid notification_webhook_url: {err}")
            await set_app_setting("notification_webhook_url", clean_nw)
            self._notification_webhook_url = clean_nw
            updated_keys.append("notification_webhook_url")

        if req.ntfy_topic is not None:
            await set_app_setting("ntfy_topic", req.ntfy_topic.strip())
            self._ntfy_topic = req.ntfy_topic.strip()
            updated_keys.append("ntfy_topic")

        if req.ntfy_server_url is not None:
            clean_ntfy = req.ntfy_server_url.strip().rstrip("/")
            if clean_ntfy:
                valid, err = validate_external_url(clean_ntfy)
                if not valid:
                    raise HTTPException(status_code=400, detail=f"Invalid ntfy_server_url: {err}")
            await set_app_setting("ntfy_server_url", clean_ntfy)
            self._ntfy_server_url = clean_ntfy
            updated_keys.append("ntfy_server_url")

        if req.admin_phone_numbers is not None:
            await set_app_setting("admin_phone_numbers", req.admin_phone_numbers.strip())
            self._admin_phone_numbers = req.admin_phone_numbers.strip()
            updated_keys.append("admin_phone_numbers")

        if req.telegram_enabled is not None:
            await set_app_setting("telegram_enabled", str(req.telegram_enabled).lower())
            self._telegram_enabled = req.telegram_enabled
            updated_keys.append("telegram_enabled")

        if req.telegram_bot_token is not None:
            clean_tg = req.telegram_bot_token.strip()
            if clean_tg and not clean_tg.startswith("••"):
                encrypted = self.encrypt_secret(clean_tg)
                await set_app_setting("telegram_bot_token", encrypted, is_secret=True)
                self._telegram_bot_token = clean_tg
                updated_keys.append("telegram_bot_token")
            elif clean_tg == "":
                await set_app_setting("telegram_bot_token", "", is_secret=True)
                self._telegram_bot_token = None
                updated_keys.append("telegram_bot_token")

        if req.telegram_admin_chat_ids is not None:
            await set_app_setting("telegram_admin_chat_ids", req.telegram_admin_chat_ids.strip())
            self._telegram_admin_chat_ids = req.telegram_admin_chat_ids.strip()
            updated_keys.append("telegram_admin_chat_ids")

        if req.default_lease_duration_hours is not None:
            await set_app_setting("default_lease_duration_hours", str(req.default_lease_duration_hours))
            self._default_lease_duration_hours = req.default_lease_duration_hours
            updated_keys.append("default_lease_duration_hours")

        if req.default_invite_expiry_days is not None:
            await set_app_setting("default_invite_expiry_days", str(req.default_invite_expiry_days))
            self._default_invite_expiry_days = req.default_invite_expiry_days
            updated_keys.append("default_invite_expiry_days")

        if req.auth_method is not None:
            clean_am = req.auth_method.strip().lower()
            if clean_am in ("none", "password", "oidc", "forward_auth"):
                await set_app_setting("auth_method", clean_am)
                settings.AUTH_METHOD = clean_am
                updated_keys.append("auth_method")

        if req.admin_password is not None:
            clean_pw = req.admin_password.strip()
            if clean_pw:
                hashed = hash_password(clean_pw)
                await set_app_setting("admin_password_hash", hashed, is_secret=True)
                self._admin_password_hash = hashed
                settings.ADMIN_PASSWORD = clean_pw
                updated_keys.append("admin_password")

        if req.webhook_secret is not None:
            clean_ws = req.webhook_secret.strip()
            if clean_ws and not clean_ws.startswith("••"):
                encrypted = self.encrypt_secret(clean_ws)
                await set_app_setting("webhook_secret", encrypted, is_secret=True)
                self._webhook_secret = clean_ws
                settings.WEBHOOK_SECRET = clean_ws
                updated_keys.append("webhook_secret")
            elif clean_ws == "":
                await set_app_setting("webhook_secret", "", is_secret=True)
                self._webhook_secret = None
                settings.WEBHOOK_SECRET = None
                updated_keys.append("webhook_secret")

        if req.app_url is not None:
            clean_app_url = req.app_url.strip().rstrip("/")
            if clean_app_url:
                valid, err = validate_external_url(clean_app_url)
                if not valid:
                    raise HTTPException(status_code=400, detail=f"Invalid app_url: {err}")
            await set_app_setting("app_url", clean_app_url)
            self._app_url = clean_app_url
            updated_keys.append("app_url")

        if req.oidc_client_id is not None:
            clean_cid = req.oidc_client_id.strip()
            await set_app_setting("oidc_client_id", clean_cid)
            settings.OIDC_CLIENT_ID = clean_cid
            updated_keys.append("oidc_client_id")

        if req.oidc_client_secret is not None:
            clean_cs = req.oidc_client_secret.strip()
            if clean_cs and not clean_cs.startswith("••"):
                encrypted = self.encrypt_secret(clean_cs)
                await set_app_setting("oidc_client_secret", encrypted, is_secret=True)
                settings.OIDC_CLIENT_SECRET = clean_cs
                updated_keys.append("oidc_client_secret")
            elif clean_cs == "":
                await set_app_setting("oidc_client_secret", "", is_secret=True)
                settings.OIDC_CLIENT_SECRET = None
                updated_keys.append("oidc_client_secret")

        if req.oidc_issuer_url is not None:
            clean_iss = req.oidc_issuer_url.strip().rstrip("/")
            if clean_iss:
                valid, err = validate_external_url(clean_iss)
                if not valid:
                    raise HTTPException(status_code=400, detail=f"Invalid oidc_issuer_url: {err}")
            await set_app_setting("oidc_issuer_url", clean_iss)
            settings.OIDC_ISSUER_URL = clean_iss
            updated_keys.append("oidc_issuer_url")

        if req.oidc_redirect_uri is not None:
            clean_red = req.oidc_redirect_uri.strip()
            if clean_red:
                valid, err = validate_external_url(clean_red)
                if not valid:
                    raise HTTPException(status_code=400, detail=f"Invalid oidc_redirect_uri: {err}")
            await set_app_setting("oidc_redirect_uri", clean_red)
            settings.OIDC_REDIRECT_URI = clean_red
            updated_keys.append("oidc_redirect_uri")

        if req.oidc_admin_group is not None:
            clean_grp = req.oidc_admin_group.strip()
            await set_app_setting("oidc_admin_group", clean_grp)
            settings.OIDC_ADMIN_GROUP = clean_grp
            updated_keys.append("oidc_admin_group")

        # Sync services
        from app.services.whatsapp_service import whatsapp_service
        whatsapp_service.enabled = settings.WHATSAPP_ENABLED
        whatsapp_service.base_url = settings.WHATSAPP_SERVICE_URL.rstrip("/")

        from app.services.notification_service import notification_service
        notification_service.configure(
            ntfy_topic=self._ntfy_topic,
            ntfy_server_url=self._ntfy_server_url,
            webhook_url=self._notification_webhook_url
        )

        from app.services.telegram_service import telegram_service
        telegram_service.configure(
            enabled=self._telegram_enabled,
            bot_token=self._telegram_bot_token,
            admin_chat_ids=self._telegram_admin_chat_ids
        )

        await audit_service.log(
            actor=actor,
            action="UPDATE_SYSTEM_SETTINGS",
            target_type="SYSTEM_CONFIG",
            target_name="System Settings",
            target_id="settings",
            details=f"Updated keys: {', '.join(updated_keys)}",
            status="SUCCESS"
        )

        if any(k in updated_keys for k in ("authentik_url", "authentik_token", "app_group_prefix")):
            from app.services.matrix_service import matrix_service
            matrix_service.invalidate_cache()

        return await self.get_settings_response()

    async def test_telegram(self, req: TestTelegramRequest) -> TestTelegramResponse:
        from app.services.telegram_service import telegram_service
        token_to_test = req.token
        if not token_to_test or token_to_test.startswith("••"):
            token_to_test = self._telegram_bot_token
        return await telegram_service.test_connection(token_to_test)

    async def test_notification(self, channel: str = "all") -> Dict[str, Any]:
        from app.services.notification_service import notification_service
        return await notification_service.send_notification(
            title="🔔 Authentik Manager Test Alert",
            message="Push notifications are properly connected! You will receive live alerts when invites are claimed or guest passes expire.",
            tags=["bell", "tada"],
            priority="default"
        )

    async def test_authentik_connection(self, req: Optional[TestConnectionRequest] = None) -> TestConnectionResponse:
        if req is None:
            req = TestConnectionRequest()

        if settings.DEMO_MODE:
            return TestConnectionResponse(success=True, version="2024.8.3 (Demo)")

        url = (req.url or settings.AUTHENTIK_URL).strip().rstrip("/")
        valid, err = validate_external_url(url)
        if not valid:
            return TestConnectionResponse(success=False, error=err)

        is_custom_url = bool(req.url and req.url.strip().rstrip("/") != settings.AUTHENTIK_URL.rstrip("/"))
        if is_custom_url:
            if not req.token or req.token.startswith("••"):
                return TestConnectionResponse(
                    success=False,
                    error="Cannot use stored Authentik token when testing a custom URL. Please supply the token explicitly."
                )
            token = req.token
        else:
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
                        error=f"Authentik returned HTTP {res.status_code}"
                    )
        except httpx.ConnectError:
            return TestConnectionResponse(
                success=False,
                error="Failed to connect: Host is unreachable or connection was refused."
            )
        except httpx.ConnectTimeout:
            return TestConnectionResponse(
                success=False,
                error="Connection timed out while communicating with the specified Authentik host."
            )
        except Exception as e:
            logger.warning(f"Authentik connection test error: {e}")
            return TestConnectionResponse(
                success=False,
                error="Connection test failed: Unable to communicate with the specified host."
            )

    async def auto_setup_oidc(self, req: AutoSetupOidcRequest, actor: str = "Admin") -> AutoSetupOidcResponse:
        steps_completed = []
        logs: List[str] = []

        def log_step(msg: str, level: str = "info"):
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            entry = f"[{ts}] {msg}"
            logs.append(entry)
            if level == "error":
                logger.error(f"[OIDC Wizard] {msg}")
            elif level == "warning":
                logger.warning(f"[OIDC Wizard] {msg}")
            else:
                logger.info(f"[OIDC Wizard] {msg}")

        log_step(f"Starting OIDC setup automation. Target App: '{req.app_name}', Slug: '{req.app_slug}', Admin Group: '{req.admin_group_name}', Immediate Activation: {req.activate_immediately}")

        try:
            # 1. Verify Authentik Connection
            log_step(f"Step 1/8: Testing Authentik API connection at {settings.AUTHENTIK_URL}...")
            is_connected, conn_err = await authentik_client.test_connection()
            if not is_connected and not authentik_client.demo_mode:
                err_msg = f"Cannot connect to Authentik API: {conn_err or 'Invalid token or unreachable host'}."
                log_step(f"Step 1 Failed: {err_msg}", level="error")
                raise HTTPException(
                    status_code=400,
                    detail=f"{err_msg} Please configure Authentik URL and API token first."
                )
            log_step("Step 1 Success: Authentik API connection verified successfully")
            steps_completed.append("Verified Authentik API connection")

            # 2. Determine App URL and Redirect URI
            log_step("Step 2/8: Configuring Application URL and OAuth redirect URI...")
            raw_url = (req.app_url or self._app_url or "http://localhost:8000").strip().rstrip("/")
            if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
                raw_url = f"https://{raw_url}"
            app_url = raw_url
            redirect_uri = f"{app_url}/api/auth/oidc/callback"
            self._app_url = app_url
            await set_app_setting("app_url", app_url)
            log_step(f"Step 2 Success: Application URL = '{app_url}' | Redirect URI = '{redirect_uri}'")
            steps_completed.append(f"Configured application URL ({app_url}) and redirect URI ({redirect_uri})")

            # 3. Discover Flows
            log_step("Step 3/8: Discovering authentication and authorization flows in Authentik...")
            flows = await authentik_client.get_flows()
            log_step(f"Found {len(flows)} total flow instances in Authentik")

            auth_flow = None
            # Try designation=authorization flows
            auth_flows = [f for f in flows if str(f.get("designation") or "") == "authorization"]
            auth_flow = next((f for f in auth_flows if "implicit" in str(f.get("slug") or "").lower()), None)
            if not auth_flow:
                auth_flow = next((f for f in auth_flows if "consent" in str(f.get("slug") or "").lower()), None)
            if not auth_flow and auth_flows:
                auth_flow = auth_flows[0]

            # If not found by designation, search across all flows by slug
            if not auth_flow:
                auth_flow = next((f for f in flows if "implicit" in str(f.get("slug") or "").lower()), None)
            if not auth_flow:
                auth_flow = next((f for f in flows if "authorization" in str(f.get("slug") or "").lower()), None)
            if not auth_flow and flows:
                auth_flow = flows[0]

            if not auth_flow:
                err_msg = "No authorization flow found in Authentik. Please ensure an authorization flow exists in Authentik (e.g. 'default-provider-authorization-implicit-consent')."
                log_step(f"Step 3 Failed: {err_msg}", level="error")
                raise HTTPException(status_code=400, detail=err_msg)

            auth_flow_pk = auth_flow["pk"]
            log_step(f"Step 3 Success: Selected authorization flow '{auth_flow.get('name', 'default')}' (slug: '{auth_flow.get('slug')}', pk: {auth_flow_pk})")

            invalidation_flows = [f for f in flows if str(f.get("designation") or "") == "invalidation"]
            invalidation_flow = next((f for f in invalidation_flows if "invalidation" in str(f.get("slug") or "").lower()), None)
            if not invalidation_flow:
                invalidation_flow = next((f for f in flows if "invalidation" in str(f.get("slug") or "").lower() or "logout" in str(f.get("slug") or "").lower()), None)
            invalidation_flow_pk = invalidation_flow["pk"] if invalidation_flow else None
            if invalidation_flow:
                log_step(f"Selected invalidation/logout flow: '{invalidation_flow.get('name')}' (pk: {invalidation_flow_pk})")

            steps_completed.append(f"Selected authorization flow '{auth_flow.get('name', 'default')}'")

            # 4. Discover Scope Mappings
            log_step("Step 4/8: Discovering OpenID scope property mappings...")
            scope_mappings = await authentik_client.get_scope_mappings()
            wanted_scopes = {"openid", "email", "profile", "groups", "phone"}
            property_mappings = []
            mapped_names = []
            for sm in scope_mappings:
                sm_name = (sm.get("scope_name") or sm.get("name") or "").lower()
                sm_managed = (sm.get("managed") or "").lower()
                if any(s in sm_name or s in sm_managed for s in wanted_scopes):
                    property_mappings.append(str(sm["pk"]))
                    mapped_names.append(sm.get("name") or sm.get("scope_name"))
            log_step(f"Step 4 Success: Mapped {len(property_mappings)} standard scopes: {', '.join(mapped_names) if mapped_names else 'none'}")
            steps_completed.append(f"Mapped {len(property_mappings)} standard OIDC scopes (openid, email, profile, groups, phone)")

            # 5. Check or Create OAuth2 Provider
            provider_name = req.app_name or "Authentik Access Manager"
            log_step(f"Step 5/8: Querying existing OAuth2 Providers in Authentik for '{provider_name}'...")
            existing_providers = await authentik_client.get_oauth2_providers()
            target_provider = next(
                (p for p in existing_providers if str(p.get("name") or "").strip().lower() == provider_name.strip().lower()),
                None
            )

            if target_provider:
                provider_pk = target_provider["pk"]
                log_step(f"Found existing OAuth2 Provider '{provider_name}' (ID: {provider_pk}). Updating configuration...")
                client_id = target_provider.get("client_id") or f"authentik-manager-{secrets.token_hex(12)}"
                client_secret = settings.OIDC_CLIENT_SECRET or target_provider.get("client_secret") or secrets.token_urlsafe(32)
                cur_uris = target_provider.get("redirect_uris", [])
                has_uri = any(
                    (u.get("url") == redirect_uri if isinstance(u, dict) else str(u) == redirect_uri)
                    for u in cur_uris
                )
                update_data: Dict[str, Any] = {"client_secret": client_secret}
                if not has_uri:
                    log_step(f"Adding redirect URI '{redirect_uri}' to existing provider...")
                    cur_uris.append({"matching_mode": "strict", "url": redirect_uri})
                    update_data["redirect_uris"] = cur_uris

                if property_mappings:
                    existing_pms = [str(x) for x in target_provider.get("property_mappings", [])]
                    merged_pms = list(dict.fromkeys(existing_pms + property_mappings))
                    update_data["property_mappings"] = merged_pms
                    log_step(f"Ensuring {len(merged_pms)} scope mappings attached to existing provider")

                await authentik_client.update_oauth2_provider(provider_pk, update_data)
                log_step(f"Step 5 Success: Updated existing OAuth2 Provider '{provider_name}' (ID: {provider_pk})")
                steps_completed.append(f"Updated existing OAuth2 Provider '{provider_name}' (ID: {provider_pk})")
            else:
                log_step(f"No existing provider '{provider_name}' found. Creating new OAuth2 Provider...")
                client_id = f"authentik-manager-{secrets.token_hex(12)}"
                client_secret = secrets.token_urlsafe(32)
                created_provider = await authentik_client.create_oauth2_provider(
                    name=provider_name,
                    authorization_flow=str(auth_flow_pk),
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uris=[redirect_uri],
                    property_mappings=property_mappings if property_mappings else None,
                    invalidation_flow=str(invalidation_flow_pk) if invalidation_flow_pk else None,
                    issuer_mode="per_provider"
                )
                provider_pk = created_provider["pk"]
                log_step(f"Step 5 Success: Created OAuth2 Provider '{provider_name}' (ID: {provider_pk}, Client ID: {client_id})")
                steps_completed.append(f"Created OAuth2 Provider '{provider_name}' in Authentik (Client ID: {client_id})")

            # 6. Check or Create Application in Authentik
            app_slug = req.app_slug or "authentik-manager"
            log_step(f"Step 6/8: Checking if Application '{app_slug}' exists in Authentik...")
            existing_app = await authentik_client.get_application_by_slug(app_slug)
            if not existing_app:
                apps = await authentik_client.get_applications()
                existing_app = next((a for a in apps if str(a.get("slug") or "").lower() == app_slug.lower()), None)

            if existing_app:
                app_pk = str(existing_app["pk"])
                log_step(f"Found existing Application '{app_slug}' (PK: {app_pk}). Updating provider binding to provider #{provider_pk}...")
                await authentik_client.update_application(
                    app_slug,
                    {
                        "name": provider_name,
                        "provider": int(provider_pk),
                        "meta_launch_url": f"{app_url}/",
                    }
                )
                log_step(f"Step 6 Success: Attached provider #{provider_pk} to Application '{app_slug}'")
                steps_completed.append(f"Attached provider to existing Application '{app_slug}'")
            else:
                log_step(f"Creating new Application '{provider_name}' (slug: '{app_slug}') bound to provider #{provider_pk}...")
                created_app = await authentik_client.create_application(
                    name=provider_name,
                    slug=app_slug,
                    provider_pk=int(provider_pk),
                    meta_launch_url=f"{app_url}/",
                    meta_description="Permission Matrix, RBAC Management & Mobile Bot for Authentik",
                    meta_icon="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/authentik.svg",
                    open_in_new_tab=True
                )
                app_pk = str(created_app["pk"])
                log_step(f"Step 6 Success: Created Application '{app_slug}' in Authentik (PK: {app_pk})")
                steps_completed.append(f"Created Application '{app_slug}' in Authentik")

            # 7. Restrict Access via Policy Binding to Admin Group
            admin_group_name = req.admin_group_name or "authentik Admins"
            log_step(f"Step 7/8: Enforcing RBAC access restriction for group '{admin_group_name}'...")
            bound_group_pk = None
            try:
                groups = await authentik_client.get_groups()
                admin_group = next(
                    (g for g in groups if str(g.get("name") or "").strip().lower() == admin_group_name.strip().lower()),
                    None
                )
                if admin_group:
                    bound_group_pk = str(admin_group["pk"])
                    log_step(f"Found admin group '{admin_group_name}' (PK: {bound_group_pk}). Checking existing policy bindings...")
                    bindings = await authentik_client.get_policy_bindings(target_pk=app_pk)
                    existing_binding = next((b for b in bindings if str(b.get("group")) == bound_group_pk), None)
                    if not existing_binding:
                        log_step(f"Binding group '{admin_group_name}' to Application '{app_slug}'...")
                        await authentik_client.create_policy_binding(
                            target_pk=app_pk,
                            group_pk=bound_group_pk,
                            order=0,
                            negate=False
                        )
                        log_step(f"Created policy binding for group '{admin_group_name}'")
                    else:
                        log_step(f"Group '{admin_group_name}' is already bound to Application '{app_slug}'")
                    await authentik_client.set_app_policy_engine_mode(app_slug, "any")
                    log_step("Enforced Application policy engine mode = 'any'")
                    steps_completed.append(f"Enforced access restriction: bound group '{admin_group_name}' to Application")
                else:
                    log_step(f"Note: Admin group '{admin_group_name}' was not found in Authentik groups", level="warning")
                    steps_completed.append(f"Note: Admin group '{admin_group_name}' was not found in Authentik groups")
            except Exception as e:
                log_step(f"Warning: Could not bind admin group to application: {e}", level="warning")
                steps_completed.append(f"Note: Admin group access binding skipped: {str(e)}")

            # 8. Save OIDC Settings in database
            log_step("Step 8/8: Saving OIDC configuration into local database...")
            issuer_url = f"{settings.AUTHENTIK_URL.rstrip('/')}/application/o/{app_slug}/"
            encrypted_secret = self.encrypt_secret(client_secret)

            await set_app_setting("oidc_client_id", client_id)
            await set_app_setting("oidc_client_secret", encrypted_secret, is_secret=True)
            await set_app_setting("oidc_issuer_url", issuer_url)
            await set_app_setting("oidc_redirect_uri", redirect_uri)
            await set_app_setting("oidc_admin_group", admin_group_name)

            settings.OIDC_CLIENT_ID = client_id
            settings.OIDC_CLIENT_SECRET = client_secret
            settings.OIDC_ISSUER_URL = issuer_url
            settings.OIDC_REDIRECT_URI = redirect_uri
            settings.OIDC_ADMIN_GROUP = admin_group_name

            if req.activate_immediately:
                await set_app_setting("auth_method", "oidc")
                settings.AUTH_METHOD = "oidc"
                log_step("Activated Authentik OIDC Single Sign-On as active authentication method")
                steps_completed.append("Activated Authentik OIDC Single Sign-On as active authentication method")
            else:
                log_step("OIDC credentials saved. Authentication method left unchanged.")
                steps_completed.append("Saved OIDC configuration (Authentication method unchanged)")

            # 9. Audit Log
            await audit_service.log(
                actor=actor,
                action="OIDC_AUTO_SETUP",
                target_type="AUTH",
                target_name=app_slug,
                details=f"Automated OIDC setup: Provider {provider_name} (ID: {provider_pk}), App {app_slug}, Group '{admin_group_name}'. Active method: {settings.AUTH_METHOD}",
                status="SUCCESS"
            )
            log_step("OIDC Automation Completed Successfully!")

            return AutoSetupOidcResponse(
                success=True,
                message="Authentik OIDC / Single Sign-On setup completed successfully!",
                app_url=app_url,
                provider_pk=provider_pk,
                provider_name=provider_name,
                client_id=client_id,
                client_secret_masked=self._mask_token(client_secret),
                issuer_url=issuer_url,
                redirect_uri=redirect_uri,
                application_pk=app_pk,
                application_slug=app_slug,
                bound_group_name=admin_group_name,
                bound_group_pk=bound_group_pk,
                auth_method=settings.AUTH_METHOD,
                steps_completed=steps_completed,
                logs=logs
            )

        except HTTPException as he:
            err_msg = he.detail if isinstance(he.detail, str) else str(he.detail)
            log_step(f"Setup aborted with HTTP {he.status_code}: {err_msg}", level="error")
            await audit_service.log(
                actor=actor,
                action="OIDC_AUTO_SETUP_FAILED",
                target_type="AUTH",
                target_name=req.app_slug or "authentik-manager",
                details=f"OIDC auto setup failed: {err_msg}",
                status="FAILED"
            )
            raise HTTPException(
                status_code=he.status_code,
                detail={"error": err_msg, "logs": logs, "steps_completed": steps_completed}
            )
        except Exception as e:
            err_msg = str(e)
            log_step(f"Unexpected error during OIDC setup: {err_msg}", level="error")
            logger.exception(f"[OIDC Wizard] Unexpected exception: {err_msg}")
            await audit_service.log(
                actor=actor,
                action="OIDC_AUTO_SETUP_FAILED",
                target_type="AUTH",
                target_name=req.app_slug or "authentik-manager",
                details=f"OIDC auto setup failed: {err_msg}",
                status="FAILED"
            )
            raise HTTPException(
                status_code=400,
                detail={"error": err_msg, "logs": logs, "steps_completed": steps_completed}
            )

settings_service = SettingsService()
