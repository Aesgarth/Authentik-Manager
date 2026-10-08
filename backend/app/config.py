import os
import secrets
import logging
from typing import Optional, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.security import resolve_secret_key, is_insecure_password, is_placeholder_secret_key

logger = logging.getLogger("authentik_manager.config")

def resolve_bridge_secret(configured_secret: Optional[str], data_dir: str = "data") -> str:
    """
    Ensures a dedicated internal shared secret exists for the WhatsApp bridge:
    1. If configured in environment and not a placeholder, use it.
    2. Otherwise, read from data/.bridge_secret.
    3. If neither exists, generates a secure random 64-char key and stores in data/.bridge_secret.
    Never falls back to SECRET_KEY to prevent bridge compromises from allowing JWT forgery.
    """
    clean = (configured_secret or "").strip()
    if clean and not is_placeholder_secret_key(clean):
        return clean

    secret_file = os.path.join(data_dir, ".bridge_secret")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if len(val) >= 32 and not is_placeholder_secret_key(val):
                    return val
    except Exception as e:
        logger.warning(f"Could not read bridge secret file {secret_file}: {e}")

    gen = secrets.token_hex(32)
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(gen)
        if hasattr(os, "chmod"):
            try:
                os.chmod(secret_file, 0o600)
            except Exception:
                pass
        logger.info(f"Generated new secure persistent bridge secret in {secret_file}")
    except Exception as e:
        logger.warning(f"Could not persist bridge secret to {secret_file}: {e}")

    return gen

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App Settings
    APP_NAME: str = "Authentik Access Manager"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    SECRET_KEY: str = ""
    SQLITE_DB_PATH: str = "data/manager.db"
    LOG_LEVEL: str = "INFO"

    # Authentik Connection
    AUTHENTIK_URL: str = "https://authentik.company"
    AUTHENTIK_TOKEN: str = ""
    AUTHENTIK_INSECURE_SKIP_VERIFY: bool = False
    
    # App Group & RBAC Policy Options
    APP_GROUP_PREFIX: str = "App - "
    DEFAULT_ENROLLMENT_FLOW: str = "default-enrollment-flow"

    # Security & Tool Authentication: 'password' (default), 'forward_auth', 'oidc', or 'none' (insecure)
    AUTH_METHOD: Literal["none", "password", "forward_auth", "oidc"] = "password"
    ADMIN_PASSWORD: str = ""
    ALLOW_BREAKGLASS: bool = False
    WEBHOOK_SECRET: Optional[str] = None
    INTERNAL_SERVICE_SECRET: Optional[str] = None
    CORS_ORIGINS: str = ""
    COOKIE_SECURE: bool = False
    
    # OIDC Configuration (for when AUTH_METHOD="oidc")
    OIDC_ISSUER_URL: Optional[str] = None      # e.g., https://auth.lan/application/o/authentik-manager/
    OIDC_CLIENT_ID: Optional[str] = None
    OIDC_CLIENT_SECRET: Optional[str] = None
    OIDC_REDIRECT_URI: Optional[str] = None    # e.g., https://manager.lan/api/auth/oidc/callback
    OIDC_ADMIN_GROUP: str = "authentik Admins" # Group required to access manager

    # Forward-Auth Header Options (when behind Authentik Proxy Outpost)
    FORWARD_AUTH_HEADER_USER: str = "x-authentik-username"
    FORWARD_AUTH_HEADER_GROUPS: str = "x-authentik-groups"
    FORWARD_AUTH_TRUSTED_PROXIES: str = "127.0.0.1,::1"

    # WhatsApp Integration (via Baileys Microservice)
    WHATSAPP_ENABLED: bool = True
    WHATSAPP_SERVICE_URL: str = "http://127.0.0.1:3001"
    DEFAULT_COUNTRY_CODE: str = "44"

    # Demo Mode: ONLY enabled if explicitly set to true in .env (never auto-enabled)
    DEMO_MODE: bool = False

settings = Settings()

# Automatically resolve a secure, persistent SECRET_KEY if default was left in place
data_dir = os.path.dirname(settings.SQLITE_DB_PATH) or "data"
settings.SECRET_KEY = resolve_secret_key(settings.SECRET_KEY, data_dir=data_dir)

# Automatically resolve a dedicated INTERNAL_SERVICE_SECRET for local bridge
settings.INTERNAL_SERVICE_SECRET = resolve_bridge_secret(settings.INTERNAL_SERVICE_SECRET, data_dir=data_dir)

# Log startup security warnings
if settings.AUTH_METHOD == "none":
    logger.warning("=" * 70)
    logger.warning("CRITICAL SECURITY WARNING: AUTH_METHOD is set to 'none'!")
    logger.warning("Anyone who can access this port has full administrative control.")
    logger.warning("=" * 70)

if is_insecure_password(settings.ADMIN_PASSWORD) and settings.AUTH_METHOD == "password":
    logger.info("ADMIN_PASSWORD is not configured in .env; checking for persistent database credentials...")
