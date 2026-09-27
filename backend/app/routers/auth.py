import secrets
import httpx
from typing import Optional
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from app.config import settings
from app.auth import create_access_token, decode_access_token, get_current_user
from app.models import LoginRequest, AuthStatus
from app.services.audit_service import audit_service

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
    if settings.AUTH_METHOD != "password":
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

@router.get("/oidc/login")
async def oidc_login(request: Request):
    """Initiates OAuth2/OIDC authorization code flow with Authentik."""
    if settings.AUTH_METHOD != "oidc":
        raise HTTPException(status_code=400, detail="OIDC is not the configured AUTH_METHOD")

    if not settings.OIDC_CLIENT_ID or not settings.OIDC_ISSUER_URL:
        raise HTTPException(
            status_code=500,
            detail="OIDC_CLIENT_ID or OIDC_ISSUER_URL is missing in configuration"
        )

    state = secrets.token_urlsafe(16)
    redirect_uri = settings.OIDC_REDIRECT_URI or str(request.url_for("oidc_callback"))

    # Issuer URL typically ends with /application/o/<slug>/
    issuer = settings.OIDC_ISSUER_URL.rstrip("/")
    auth_endpoint = f"{issuer}/protocol/openid-connect/auth" if not issuer.endswith("/application/o/authorize/") else issuer
    # In Authentik, /application/o/authorize/ or OpenID Connect auth
    if "/application/o/" in issuer and not issuer.endswith("/auth"):
        auth_endpoint = f"{issuer}/authorize/"

    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid profile email groups",
        "state": state,
    }
    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(key="oidc_state", value=state, httponly=True, max_age=300)
    return response

@router.get("/oidc/callback")
async def oidc_callback(request: Request, response: Response, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Processes OIDC authorization code and establishes session."""
    if error:
        raise HTTPException(status_code=400, detail=f"OIDC error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    saved_state = request.cookies.get("oidc_state")
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state (CSRF check failed)")

    issuer = settings.OIDC_ISSUER_URL.rstrip("/")
    token_endpoint = f"{issuer}/token/" if "/application/o/" in issuer else f"{issuer}/protocol/openid-connect/token"
    userinfo_endpoint = f"{issuer}/userinfo/" if "/application/o/" in issuer else f"{issuer}/protocol/openid-connect/userinfo"

    redirect_uri = settings.OIDC_REDIRECT_URI or str(request.url_for("oidc_callback"))

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
            raise HTTPException(status_code=400, detail=f"Failed to exchange token: {token_res.text}")
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")

        # Fetch user profile
        user_res = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch userinfo from Authentik")
        
        userinfo = user_res.json()

    username = userinfo.get("preferred_username") or userinfo.get("nickname") or userinfo.get("name") or "User"
    user_groups = userinfo.get("groups", [])

    # Check if user is member of required admin group
    required_group = settings.OIDC_ADMIN_GROUP
    if required_group and required_group not in user_groups and "authentik Admins" not in user_groups:
        await audit_service.log(
            actor=username,
            action="OIDC_LOGIN_DENIED",
            target_type="AUTH",
            target_name=username,
            details=f"User lacks required admin group: {required_group}",
            status="FAILED"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Access Denied: You must be a member of the '{required_group}' group in Authentik."
        )

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
        details="Logged in via Authentik OIDC",
        status="SUCCESS"
    )
    return redirect
