import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import get_current_user
from app.models import (
    SettingsResponse,
    UpdateSettingsRequest,
    TestConnectionRequest,
    TestConnectionResponse,
    TestNotificationRequest,
    TestNotificationResponse,
    TestTelegramRequest,
    TestTelegramResponse,
    AutoSetupOidcRequest,
    AutoSetupOidcResponse,
)
from app.services.settings_service import settings_service

logger = logging.getLogger("authentik_manager.routers.settings")

router = APIRouter(prefix="/api/settings", tags=["Settings & Administration"])

@router.get("", response_model=SettingsResponse)
async def get_settings(current_user: dict = Depends(get_current_user)):
    return await settings_service.get_settings_response()

@router.put("", response_model=SettingsResponse)
async def update_settings(
    req: UpdateSettingsRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    return await settings_service.update_settings(req, actor=actor)

@router.post("/test-authentik", response_model=TestConnectionResponse)
async def test_authentik_connection(
    req: TestConnectionRequest,
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.test_authentik_connection(req)

@router.post("/test-notification", response_model=TestNotificationResponse)
async def test_notification(
    req: TestNotificationRequest,
    current_user: dict = Depends(get_current_user)
):
    results = await settings_service.test_notification(req.channel)
    has_success = any(r.get("success", False) for r in results.values()) if results else False
    if not results:
        results = {"status": "No push notification channel (NTFY topic or Webhook URL) is configured."}
    return TestNotificationResponse(success=has_success, results=results)

@router.post("/test-telegram", response_model=TestTelegramResponse)
async def test_telegram_connection(
    req: TestTelegramRequest,
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.test_telegram(req)

@router.post("/auto-setup-oidc", response_model=AutoSetupOidcResponse)
async def auto_setup_oidc(
    req: AutoSetupOidcRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    logger.info(f"Received /api/settings/auto-setup-oidc request from '{actor}' for app '{req.app_name}' ({req.app_url})")
    try:
        res = await settings_service.auto_setup_oidc(req, actor=actor)
        logger.info(f"OIDC setup succeeded for '{req.app_name}': Provider PK={res.provider_pk}, Client ID={res.client_id}")
        return res
    except HTTPException as he:
        logger.error(f"OIDC setup failed with HTTPException {he.status_code}: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"OIDC setup failed with unhandled exception: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail={"error": str(e)})

@router.get("/detect-url")
async def detect_url(request: Request, current_user: dict = Depends(get_current_user)):
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", str(request.base_url.netloc)))
    detected = f"{proto}://{host}".rstrip("/")
    saved = settings_service._app_url
    return {
        "detected_url": detected,
        "saved_url": saved or detected,
        "redirect_uri": f"{(saved or detected)}/api/auth/oidc/callback"
    }

@router.post("/ensure-phone-scope")
async def ensure_phone_scope(current_user: dict = Depends(get_current_user)):
    from app.authentik_client import authentik_client
    return await authentik_client.ensure_phone_scope_mapping()


