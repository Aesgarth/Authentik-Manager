import os
import logging
from typing import Optional, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.security import resolve_secret_key

logger = logging.getLogger("authentik_manager.config")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App Settings
    APP_NAME: str = "Authentik Access Manager"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "changeme-in-production-use-a-strong-secret-key-32chars"
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
    ADMIN_PASSWORD: str = "admin123"
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
    FORWARD_AUTH_TRUSTED_PROXIES: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

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

if not settings.INTERNAL_SERVICE_SECRET:
    settings.INTERNAL_SERVICE_SECRET = settings.SECRET_KEY

# Log startup security warnings
if settings.AUTH_METHOD == "none":
    logger.warning("=" * 70)
    logger.warning("CRITICAL SECURITY WARNING: AUTH_METHOD is set to 'none'!")
    logger.warning("Anyone who can access this port has full administrative control.")
    logger.warning("=" * 70)

if settings.ADMIN_PASSWORD == "admin123" and settings.AUTH_METHOD == "password":
    logger.warning("SECURITY WARNING: ADMIN_PASSWORD is set to the default 'admin123'. Change it in settings!")
