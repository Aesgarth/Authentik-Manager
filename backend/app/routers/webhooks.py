import asyncio
import json
import logging
import secrets
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.invite_service import invite_service
from app.services.settings_service import settings_service
from app.services.audit_service import audit_service
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
    client_ip = request.client.host if request.client else "unknown"
    provided_token = request.query_params.get("token") or request.headers.get("X-Webhook-Token") or request.headers.get("Authorization")

    logger.info(f"Incoming webhook request from {client_ip} (method={request.method}, url={request.url})")

    if not verify_webhook_token(request):
        masked_token = f"{provided_token[:6]}..." if provided_token and len(provided_token) > 6 else (provided_token or "[NONE]")
        logger.warning(f"Rejected unauthorized webhook request from {client_ip}: provided token='{masked_token}' does not match configured secret.")
        try:
            await audit_service.log(
                actor="AUTHENTIK_WEBHOOK",
                action="WEBHOOK_AUTH_FAILED",
                target_type="WEBHOOK",
                target_name=client_ip,
                target_id=client_ip,
                details=f"Rejected request from {client_ip}: secret token mismatch (received: '{masked_token}')",
                status="FAILED"
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=401,
            detail="Unauthorized webhook request: missing or invalid secret token. Pass via ?token=<SECRET> or X-Webhook-Token header."
        )

    try:
        payload = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON payload on /api/webhooks/authentik from {client_ip}: {e}")
        try:
            await audit_service.log(
                actor="AUTHENTIK_WEBHOOK",
                action="WEBHOOK_PAYLOAD_INVALID",
                target_type="WEBHOOK",
                target_name=client_ip,
                target_id=client_ip,
                details=f"Invalid JSON payload received from {client_ip}: {e}",
                status="FAILED"
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")

    email = (
        payload.get("email")
        or payload.get("event_user_email")
        or payload.get("user_email")
        or (payload.get("user", {}).get("email") if isinstance(payload.get("user"), dict) else None)
    )
    inv_pk = (
        payload.get("invitation_pk")
        or payload.get("itoken")
        or (payload.get("context", {}).get("invitation", {}).get("pk") if isinstance(payload.get("context"), dict) and isinstance(payload.get("context", {}).get("invitation"), dict) else None)
    )

    logger.info(f"Authentik webhook verified successfully from {client_ip}. Payload summary: email='{email}', inv_pk='{inv_pk}'")

    try:
        await audit_service.log(
            actor="AUTHENTIK_WEBHOOK",
            action="WEBHOOK_RECEIVED",
            target_type="WEBHOOK",
            target_name=str(email or "unknown"),
            target_id=str(inv_pk or client_ip),
            details=f"Received webhook from {client_ip}. Target email: {email}, Inv PK: {inv_pk}. Raw: {json.dumps(payload)[:250]}",
            status="SUCCESS"
        )
    except Exception:
        pass

    # Process group assignment with immediate tracking and logging
    async def process_with_retry():
        try:
            # Short sleep to guarantee Authentik DB write is committed
            await asyncio.sleep(1.0)
            res = await invite_service.handle_webhook_event(payload)
            logger.info(f"Webhook processing result for {email}: {res}")

            status = res.get("status")
            if status == "success":
                await audit_service.log(
                    actor="AUTHENTIK_WEBHOOK",
                    action="WEBHOOK_PROCESSED",
                    target_type="USER",
                    target_name=res.get("user", str(email)),
                    target_id=str(res.get("user_pk", "")),
                    details=f"Successfully fulfilled invite #{res.get('invite_id')}. Assigned {res.get('assigned_groups_count')} groups to {res.get('user')}.",
                    status="SUCCESS"
                )
            elif status == "pending_sync":
                await audit_service.log(
                    actor="AUTHENTIK_WEBHOOK",
                    action="WEBHOOK_PENDING_SYNC",
                    target_type="USER",
                    target_name=str(email or "unknown"),
                    target_id=str(inv_pk or ""),
                    details=f"User {email} not yet committed to Authentik DB. Handed off to background sync worker.",
                    status="WARNING"
                )
            else:
                await audit_service.log(
                    actor="AUTHENTIK_WEBHOOK",
                    action="WEBHOOK_IGNORED",
                    target_type="WEBHOOK",
                    target_name=str(email or "unknown"),
                    target_id=str(inv_pk or ""),
                    details=f"Webhook ignored: {res.get('reason', res.get('message', 'No pending invite matched'))}",
                    status="WARNING"
                )
        except Exception as err:
            logger.error(f"Error processing Authentik webhook in background: {err}", exc_info=True)
            try:
                await audit_service.log(
                    actor="AUTHENTIK_WEBHOOK",
                    action="WEBHOOK_ERROR",
                    target_type="WEBHOOK",
                    target_name=str(email or "unknown"),
                    target_id=str(inv_pk or ""),
                    details=f"Internal error processing webhook: {err}",
                    status="FAILED"
                )
            except Exception:
                pass

    background_tasks.add_task(process_with_retry)

    return {
        "status": "received",
        "message": "Webhook accepted for processing",
        "email": email,
        "invitation_pk": inv_pk
    }
