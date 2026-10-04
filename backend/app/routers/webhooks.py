import asyncio
import logging
import secrets
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.invite_service import invite_service
from app.services.settings_service import settings_service
from app.config import settings

logger = logging.getLogger("authentik_manager.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

def verify_webhook_token(request: Request) -> bool:
    """
    Validates incoming webhook authenticity.
    If WEBHOOK_SECRET is configured, requests must provide matching token via:
      1. Query param: ?token=<SECRET> or ?secret=<SECRET>
      2. HTTP Header: X-Webhook-Token: <SECRET> or X-Authentik-Token: <SECRET>
      3. HTTP Header: Authorization: Bearer <SECRET>
    If no secret is configured, requests are accepted openly.
    """
    expected_secret = getattr(settings, "WEBHOOK_SECRET", None) or settings_service.get_webhook_secret()
    if not expected_secret:
        return True

    # 1. Query parameter
    token_param = request.query_params.get("token") or request.query_params.get("secret")
    if token_param and secrets.compare_digest(token_param, expected_secret):
        return True

    # 2. Custom header
    header_token = request.headers.get("X-Webhook-Token") or request.headers.get("X-Authentik-Token")
    if header_token and secrets.compare_digest(header_token, expected_secret):
        return True

    # 3. Authorization Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_val = auth_header[7:].strip()
        if secrets.compare_digest(bearer_val, expected_secret):
            return True

    return False

@router.get("/authentik/status")
async def webhook_status():
    """
    Returns the webhook configuration, endpoint URL, security status, and sample integration snippets.
    """
    base_host = settings.APP_HOST if settings.APP_HOST not in ("0.0.0.0", "") else "authentik-manager"
    secret = getattr(settings, "WEBHOOK_SECRET", None) or settings_service.get_webhook_secret()
    example_url = f"http://{base_host}:{settings.APP_PORT}/api/webhooks/authentik"
    if secret:
        example_url += f"?token={secret}"

    return {
        "status": "active",
        "webhook_endpoint": "/api/webhooks/authentik",
        "recommended_webhook_url": example_url,
        "token_protected": bool(secret),
        "supported_auth_methods": [
            "Query parameter: ?token=<SECRET>",
            "HTTP Header: X-Webhook-Token: <SECRET>",
            "HTTP Header: Authorization: Bearer <SECRET>"
        ],
        "supported_payloads": [
            "Authentik Generic Notification Transport (event_user_email, event_user_username)",
            "Direct Python Expression Policy HTTP ping (email, username, invitation_pk)",
            "Authentik Raw Event (action, user, context)"
        ]
    }

@router.post("/authentik")
async def handle_authentik_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives notification from Authentik when a user signs up, logs in, or redeems an invite.
    Immediately assigns the pre-selected application groups via Authentik REST API.
    """
    if not verify_webhook_token(request):
        logger.warning("Rejected unauthorized webhook request: missing or invalid secret token.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized webhook request: missing or invalid secret token. Pass via ?token=<SECRET> or X-Webhook-Token header."
        )

    try:
        payload = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON payload on /api/webhooks/authentik: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")

    logger.info(f"Received Authentik webhook notification: {payload}")

    # Process group assignment in background with a slight delay to ensure Authentik DB commit
    async def process_with_retry():
        try:
            # Short sleep to guarantee Authentik has finished writing the new user to DB
            await asyncio.sleep(1.0)
            res = await invite_service.handle_webhook_event(payload)
            logger.info(f"Webhook processing result: {res}")
        except Exception as err:
            logger.warning(f"Error processing Authentik webhook in background: {err}", exc_info=True)

    background_tasks.add_task(process_with_retry)

    return {
        "status": "received",
        "message": "Webhook accepted for processing"
    }
