import os
from typing import Optional, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App Settings
    APP_NAME: str = "Authentik Access Manager"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "changeme-in-production-use-a-strong-secret-key-32chars"
    SQLITE_DB_PATH: str = "data/manager.db"

    # Authentik Connection
    AUTHENTIK_URL: str = "https://authentik.company"
    AUTHENTIK_TOKEN: str = ""
    AUTHENTIK_INSECURE_SKIP_VERIFY: bool = False
    
    # App Group & RBAC Policy Options
    APP_GROUP_PREFIX: str = "App - "
    DEFAULT_ENROLLMENT_FLOW: str = "default-enrollment-flow"

    # Security & Tool Authentication: 'none', 'password', 'forward_auth', or 'oidc'
    AUTH_METHOD: Literal["none", "password", "forward_auth", "oidc"] = "none"
    ADMIN_PASSWORD: str = "admin123"
    
    # OIDC Configuration (for when AUTH_METHOD="oidc")
    OIDC_ISSUER_URL: Optional[str] = None      # e.g., https://auth.lan/application/o/authentik-manager/
    OIDC_CLIENT_ID: Optional[str] = None
    OIDC_CLIENT_SECRET: Optional[str] = None
    OIDC_REDIRECT_URI: Optional[str] = None    # e.g., https://manager.lan/api/auth/oidc/callback
    OIDC_ADMIN_GROUP: str = "authentik Admins" # Group required to access manager

    # Forward-Auth Header Options (when behind Authentik Proxy Outpost)
    FORWARD_AUTH_HEADER_USER: str = "x-authentik-username"
    FORWARD_AUTH_HEADER_GROUPS: str = "x-authentik-groups"

    # WhatsApp Integration (via Baileys Microservice)
    WHATSAPP_ENABLED: bool = True
    WHATSAPP_SERVICE_URL: str = "http://127.0.0.1:3001"

    # Demo / Mock Mode: allows full UI/feature exploration without live Authentik
    DEMO_MODE: bool = False

settings = Settings()

# Auto-enable demo mode if live credentials are not set or placeholder is used
if (not settings.AUTHENTIK_TOKEN or settings.AUTHENTIK_TOKEN == "your_authentik_api_bearer_token_here" or "yourdomain" in settings.AUTHENTIK_URL or "company" in settings.AUTHENTIK_URL) and not settings.DEMO_MODE:
    settings.DEMO_MODE = True
