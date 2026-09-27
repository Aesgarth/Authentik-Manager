from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import WhatsAppStatusResponse, WhatsAppSendRequest, WhatsAppSendResponse
from app.services.whatsapp_service import whatsapp_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])

@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(current_user: dict = Depends(get_current_user)):
    return await whatsapp_service.get_status()

@router.post("/send", response_model=WhatsAppSendResponse)
async def send_whatsapp_message(
    req: WhatsAppSendRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    try:
        res = await whatsapp_service.send_message(recipient=req.recipient, message=req.message)
        await audit_service.log(
            actor=actor,
            action="SEND_WHATSAPP_MESSAGE",
            target_type="COMMUNICATION",
            target_name=req.recipient,
            details="Message sent successfully via Baileys",
            status="SUCCESS"
        )
        return WhatsAppSendResponse(success=True, messageId=res.get("messageId"))
    except Exception as e:
        await audit_service.log(
            actor=actor,
            action="SEND_WHATSAPP_MESSAGE",
            target_type="COMMUNICATION",
            target_name=req.recipient,
            details=str(e),
            status="FAILED"
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout")
async def logout_whatsapp(current_user: dict = Depends(get_current_user)):
    actor = current_user.get("username", "Admin")
    try:
        res = await whatsapp_service.logout()
        await audit_service.log(
            actor=actor,
            action="WHATSAPP_LOGOUT",
            target_type="SYSTEM",
            target_name="WhatsApp Session",
            details="Disconnected WhatsApp device and cleared session",
            status="SUCCESS"
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
