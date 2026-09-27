import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from jose import jwt, JWTError
from app.config import settings

ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta_secs: int = 86400 * 7) -> str:
    to_encode = data.copy()
    expire = time.time() + expires_delta_secs
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Resolves the current authenticated user based on the configured AUTH_METHOD:
    - none: Returns default admin
    - password / oidc: Validates session JWT in cookie or Authorization header
    - forward_auth: Validates headers passed by Authentik Outpost / reverse proxy
    """
    method = settings.AUTH_METHOD

    # If demo mode or auth disabled, always allow as local admin
    if settings.DEMO_MODE or method == "none":
        return {
            "username": "admin",
            "name": "Local Administrator",
            "is_admin": True,
            "auth_method": method
        }

    # Forward-Auth mode (Authentik reverse proxy / outpost)
    if method == "forward_auth":
        username = request.headers.get(settings.FORWARD_AUTH_HEADER_USER.lower())
        if not username:
            raise HTTPException(
                status_code=401,
                detail="Missing Authentik Forward-Auth header (X-authentik-username)"
            )
        groups_header = request.headers.get(settings.FORWARD_AUTH_HEADER_GROUPS.lower(), "")
        groups = [g.strip() for g in groups_header.split(",") if g.strip()]
        is_admin = settings.OIDC_ADMIN_GROUP in groups or "authentik Admins" in groups or True

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
        "is_admin": payload.get("is_admin", True),
        "auth_method": method
    }
