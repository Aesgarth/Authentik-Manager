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
            is_admin=user.get("is_admin", True),
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
async def login_password(req: LoginRequest, response: Response):
    # Allow master admin password as breakglass even if auth method is OIDC or forward_auth
    is_master_breakglass = bool(settings.ADMIN_PASSWORD and req.password == settings.ADMIN_PASSWORD)
    if settings.AUTH_METHOD != "password" and not is_master_breakglass:
        raise HTTPException(
            status_code=400,
            detail=f"Password login not enabled (active auth method: {settings.AUTH_METHOD})"
        )

    if req.password != settings.ADMIN_PASSWORD:
        await audit_service.log(
            actor="unknown",
            action="LOGIN_ATTEMPT",
            target_type="AUTH",
            target_name="admin",
            details="Invalid password attempt",
            status="FAILED"
        )
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token({"sub": "admin", "name": "Administrator", "is_admin": True})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7
    )
    await audit_service.log(
        actor="admin",
        action="LOGIN",
        target_type="AUTH",
        target_name="admin",
        details="Successful password login",
        status="SUCCESS"
    )
    return {"status": "ok", "token": token}

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
    response.set_cookie(key="oidc_state", value=state, httponly=True, max_age=300)
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
    if not saved_state or saved_state != state:
        err_msg = f"Invalid OIDC state (CSRF check failed). Saved: '{saved_state}', Received: '{state}'"
        logger.error(f"[OIDC Callback] {err_msg}")
        return RedirectResponse(url=f"/?oidc_error={quote('Login session expired or state mismatch. Please try again.')}", status_code=status.HTTP_302_FOUND)

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
            err_msg = f"Token exchange failed (HTTP {token_res.status_code}): {token_res.text[:150]}"
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
            err_msg = f"Failed to fetch userinfo from Authentik (HTTP {user_res.status_code}): {user_res.text[:150]}"
            logger.error(f"[OIDC Callback] {err_msg}")
            return RedirectResponse(url=f"/?oidc_error={quote(err_msg)}", status_code=status.HTTP_302_FOUND)
        
        userinfo = user_res.json()
        logger.info(f"[OIDC Callback] Userinfo received: {userinfo}")

    username = userinfo.get("preferred_username") or userinfo.get("nickname") or userinfo.get("name") or "User"
    user_groups = userinfo.get("groups", [])
    logger.info(f"[OIDC Callback] Authenticated user: '{username}', Detected Groups: {user_groups}")

    # Check if user is member of required admin group
    required_group = settings.OIDC_ADMIN_GROUP
    if required_group and required_group not in user_groups and "authentik Admins" not in user_groups:
        err_msg = f"Access Denied: User '{username}' is not a member of '{required_group}'. Groups found: {user_groups}"
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
    redirect.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7
    )
    redirect.delete_cookie("oidc_state")

    await audit_service.log(
        actor=username,
        action="OIDC_LOGIN_SUCCESS",
        target_type="AUTH",
        target_name=username,
        details=f"Logged in via Authentik OIDC (groups: {user_groups})",
        status="SUCCESS"
    )
    logger.info(f"[OIDC Callback] Login complete for '{username}'. Redirecting to root dashboard.")
    return redirect
