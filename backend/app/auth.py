import time
import secrets
import logging
import ipaddress
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
import jwt
from jwt.exceptions import PyJWTError
from app.config import settings

logger = logging.getLogger("authentik_manager.auth")

ALGORITHM = "HS256"
DEFAULT_SESSION_DURATION = 86400  # 24 hours (hardened from 7 days)

def create_access_token(data: dict, expires_delta_secs: int = DEFAULT_SESSION_DURATION) -> str:
    to_encode = data.copy()
    expire = time.time() + expires_delta_secs
    to_encode.update({
        "exp": expire,
        "iat": time.time(),
        "jti": secrets.token_hex(16)
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except PyJWTError:
        return None

def is_trusted_proxy(client_ip: str, trusted_list: str) -> bool:
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
        for raw_net in trusted_list.split(","):
            raw_net = raw_net.strip()
            if not raw_net:
                continue
            if "/" in raw_net:
                if ip in ipaddress.ip_network(raw_net, strict=False):
                    return True
            else:
                if ip == ipaddress.ip_address(raw_net):
                    return True
    except Exception:
        pass
    return False

async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Resolves the current authenticated user based on the configured AUTH_METHOD:
    - none: Returns local admin (with warning)
    - password / oidc: Validates session JWT in cookie or Authorization header
    - forward_auth: Validates headers passed by trusted Authentik Outpost / reverse proxy
    """
    method = settings.AUTH_METHOD

    # If demo mode, allow as local admin
    if settings.DEMO_MODE:
        return {
            "username": "admin",
            "name": "Local Administrator",
            "is_admin": True,
            "auth_method": "demo"
        }

    # None mode: allows all operations
    if method == "none":
        return {
            "username": "admin",
            "name": "Local Administrator",
            "is_admin": True,
            "auth_method": "none"
        }

    # Forward-Auth mode (Authentik reverse proxy / outpost)
    if method == "forward_auth":
        client_ip = request.client.host if request.client else ""
        if not is_trusted_proxy(client_ip, settings.FORWARD_AUTH_TRUSTED_PROXIES):
            logger.warning(f"Forward-auth rejected request from untrusted proxy IP: '{client_ip}'")
            raise HTTPException(
                status_code=403,
                detail=f"Forward-auth rejected: request from untrusted proxy IP ({client_ip})"
            )

        username = request.headers.get(settings.FORWARD_AUTH_HEADER_USER.lower())
        if not username:
            raise HTTPException(
                status_code=401,
                detail="Missing Authentik Forward-Auth header (X-authentik-username)"
            )
        groups_header = request.headers.get(settings.FORWARD_AUTH_HEADER_GROUPS.lower(), "")
        groups = [g.strip() for g in groups_header.split(",") if g.strip()]
        
        required_group = settings.OIDC_ADMIN_GROUP or "authentik Admins"
        is_admin = (required_group in groups) or ("authentik Admins" in groups)
        if not is_admin:
            logger.warning(f"Forward-auth user '{username}' denied: not in required admin group '{required_group}'")
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: user is not a member of {required_group}"
            )

        return {
            "username": username,
            "name": username,
            "groups": groups,
            "is_admin": is_admin,
            "auth_method": "forward_auth"
        }

    # Password or OIDC mode: Inspect session token (cookie or Bearer)
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return {
        "username": payload.get("sub", "admin"),
        "name": payload.get("name", "Admin"),
        "groups": payload.get("groups", []),
        "is_admin": payload.get("is_admin", False),
        "auth_method": method
    }
