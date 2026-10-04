import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.invite_service import invite_service
from app.config import settings

logger = logging.getLogger("authentik_manager.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

@router.get("/authentik/status")
async def webhook_status():
    """
    Returns the webhook configuration, endpoint URL, and sample integration snippets.
    """
    base_host = settings.APP_HOST if settings.APP_HOST != "0.0.0.0" else "authentik-manager"
    example_url = f"http://{base_host}:{settings.APP_PORT}/api/webhooks/authentik"
    return {
        "status": "active",
        "webhook_endpoint": "/api/webhooks/authentik",
        "recommended_webhook_url": example_url,
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
