import logging
import secrets
import httpx
from typing import Optional
from urllib.parse import urlencode, quote
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from app.config import settings
from app.auth import create_access_token, decode_access_token, get_current_user
from app.models import LoginRequest, AuthStatus
from app.services.audit_service import audit_service
from app.services.settings_service import settings_service
from app.security import is_login_rate_limited, record_failed_login, reset_login_attempts

logger = logging.getLogger("authentik_manager.routers.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.get("/status", response_model=AuthStatus)
async def get_auth_status(request: Request):
    try:
        user = await get_current_user(request)
        return AuthStatus(
            authenticated=True,
            auth_method=settings.AUTH_METHOD,
            user=user.get("username"),
            is_admin=user.get("is_admin", False),
            demo_mode=settings.DEMO_MODE,
        )
    except HTTPException:
        return AuthStatus(
            authenticated=False,
            auth_method=settings.AUTH_METHOD,
            user=None,
            is_admin=False,
            demo_mode=settings.DEMO_MODE,
        )

@router.post("/login")
async def login_password(req: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting on failed login attempts
    if is_login_rate_limited(client_ip):
        logger.warning(f"Login rate limit exceeded for client IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes."
        )

    # Breakglass authentication check
    is_breakglass_active = bool(settings.ALLOW_BREAKGLASS and settings_service.verify_admin_password(req.password))
    if settings.AUTH_METHOD != "password" and not is_breakglass_active:
        raise HTTPException(
            status_code=400,
            detail=f"Password login not enabled (active auth method: {settings.AUTH_METHOD})"
        )

    # Constant-time password verification against hashed/configured admin credentials
    if not settings_service.verify_admin_password(req.password):
        record_failed_login(client_ip)
        await audit_service.log(
            actor="unknown",
            action="LOGIN_ATTEMPT",
            target_type="AUTH",
            target_name="admin",
            details=f"Invalid password attempt from {client_ip}",
            status="FAILED"
        )
        raise HTTPException(status_code=401, detail="Invalid password")

    reset_login_attempts(client_ip)

    token = create_access_token({"sub": "admin", "name": "Administrator", "is_admin": True})
    secure_cookie = (request.url.scheme == "https") or settings.COOKIE_SECURE
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=86400  # 24 hours
    )
    await audit_service.log(
        actor="admin",
        action="LOGIN",
        target_type="AUTH",
        target_name="admin",
        details="Successful password login",
        status="SUCCESS"
    )
    return {"status": "ok", "authenticated": True}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {"status": "logged_out"}

# ==================== OIDC Flow Endpoints ====================

def get_oidc_endpoints(issuer_url: str) -> tuple[str, str, str]:
    """Returns (auth_endpoint, token_endpoint, userinfo_endpoint)"""
    issuer = issuer_url.rstrip("/")
    if "/application/o/" in issuer:
        # Authentik per-provider mode: extract root Authentik URL
        root_url = issuer.split("/application/o/")[0]
        return (
            f"{root_url}/application/o/authorize/",
            f"{root_url}/application/o/token/",
            f"{root_url}/application/o/userinfo/"
        )
    return (
        f"{issuer}/protocol/openid-connect/auth",
        f"{issuer}/protocol/openid-connect/token",
        f"{issuer}/protocol/openid-connect/userinfo"
    )

@router.get("/oidc/login")
async def oidc_login(request: Request):
    """Initiates OAuth2/OIDC authorization code flow with Authentik."""
    if settings.AUTH_METHOD != "oidc":
        logger.warning(f"[OIDC Login] Rejected: AUTH_METHOD is currently '{settings.AUTH_METHOD}', not 'oidc'")
        raise HTTPException(status_code=400, detail="OIDC is not the configured AUTH_METHOD")

    if not settings.OIDC_CLIENT_ID or not settings.OIDC_ISSUER_URL:
        logger.error("[OIDC Login] Missing required settings: OIDC_CLIENT_ID or OIDC_ISSUER_URL is empty")
        raise HTTPException(
            status_code=500,
            detail="OIDC_CLIENT_ID or OIDC_ISSUER_URL is missing in configuration"
        )

    state = secrets.token_urlsafe(16)
    redirect_uri = settings.OIDC_REDIRECT_URI or str(request.url_for("oidc_callback"))

    auth_endpoint, _, _ = get_oidc_endpoints(settings.OIDC_ISSUER_URL)

    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid profile email groups",
        "state": state,
    }
    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    logger.info(f"[OIDC Login] Redirecting to Authentik authorize endpoint: {auth_endpoint} (redirect_uri: '{redirect_uri}', client_id: '{settings.OIDC_CLIENT_ID}')")

    response = RedirectResponse(url=auth_url)
    secure_cookie = (request.url.scheme == "https") or settings.COOKIE_SECURE
    response.set_cookie(key="oidc_state", value=state, httponly=True, secure=secure_cookie, max_age=300)
    return response

@router.get("/oidc/callback")
async def oidc_callback(request: Request, response: Response, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Processes OIDC authorization code and establishes session."""
    logger.info(f"[OIDC Callback] Received callback. Code present: {bool(code)}, State present: {bool(state)}, Error: {error}")
    if error:
        err_msg = f"Authentik reported error: {error}"
        logger.error(f"[OIDC Callback] {err_msg}")
        return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)
    if not code:
        err_msg = "Missing authorization code from Authentik callback"
        logger.error(f"[OIDC Callback] {err_msg}")
        return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)

    saved_state = request.cookies.get("oidc_state")
    if not saved_state or not secrets.compare_digest(saved_state, state or ""):
        err_msg = "Invalid OIDC state (CSRF check failed). Please try logging in again."
        logger.error(f"[OIDC Callback] {err_msg}")
        return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)

    _, token_endpoint, userinfo_endpoint = get_oidc_endpoints(settings.OIDC_ISSUER_URL)
    redirect_uri = settings.OIDC_REDIRECT_URI or str(request.url_for("oidc_callback"))

    logger.info(f"[OIDC Callback] Exchanging authorization code at '{token_endpoint}' for redirect_uri '{redirect_uri}'...")

    # Exchange code for tokens
    async with httpx.AsyncClient(verify=not settings.AUTHENTIK_INSECURE_SKIP_VERIFY) as client:
        token_res = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET or "",
            },
            headers={"Accept": "application/json"}
        )
        if token_res.status_code != 200:
            err_msg = f"Token exchange failed (HTTP {token_res.status_code})"
            logger.error(f"[OIDC Callback] {err_msg}")
            return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        logger.info("[OIDC Callback] Token exchange succeeded. Fetching user profile from userinfo endpoint...")

        # Fetch user profile
        user_res = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_res.status_code != 200:
            err_msg = f"Failed to fetch userinfo from Authentik (HTTP {user_res.status_code})"
            logger.error(f"[OIDC Callback] {err_msg}")
            return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)
        
        userinfo = user_res.json()
        # Redacted userinfo logging (no PII dump in production logs)
        logger.info(f"[OIDC Callback] Userinfo received for user '{userinfo.get('preferred_username', 'User')}'")

    username = userinfo.get("preferred_username") or userinfo.get("nickname") or userinfo.get("name") or "User"
    user_groups = userinfo.get("groups", [])
    logger.info(f"[OIDC Callback] Authenticated user: '{username}', Detected Groups: {user_groups}")

    # Check if user is member of required admin group (fail closed)
    required_group = (settings.OIDC_ADMIN_GROUP or "").strip() or "authentik Admins"
    if required_group not in user_groups and "authentik Admins" not in user_groups:
        err_msg = f"Access Denied: User '{username}' is not a member of '{required_group}'"
        logger.warning(f"[OIDC Callback] {err_msg}")
        await audit_service.log(
            actor=username,
            action="OIDC_LOGIN_DENIED",
            target_type="AUTH",
            target_name=username,
            details=f"User lacks required admin group: '{required_group}'. User groups: {user_groups}",
            status="FAILED"
        )
        return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)

    # Issue session JWT
    session_token = create_access_token({
        "sub": username,
        "name": userinfo.get("name", username),
        "groups": user_groups,
        "is_admin": True
    })

    redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    secure_cookie = (request.url.scheme == "https") or settings.COOKIE_SECURE
    redirect.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=86400  # 24 hours
    )
    redirect.delete_cookie("oidc_state")

    await audit_service.log(
        actor=username,
        action="OIDC_LOGIN_SUCCESS",
        target_type="AUTH",
        target_name=username,
        details="Logged in via Authentik OIDC",
        status="SUCCESS"
    )
    logger.info(f"[OIDC Callback] Login complete for '{username}'. Redirecting to root dashboard.")
    return redirect
