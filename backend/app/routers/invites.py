from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import CreateInviteRequest, TrackedInviteSchema
from app.services.invite_service import invite_service

router = APIRouter(prefix="/api/invites", tags=["Invitations"])

@router.get("", response_model=List[TrackedInviteSchema])
async def list_invites(current_user: dict = Depends(get_current_user)):
    try:
        await invite_service.sync_redemptions()
    except Exception:
        pass
    return await invite_service.list_invites()

@router.post("", response_model=TrackedInviteSchema)
async def create_invite(
    req: CreateInviteRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    try:
        return await invite_service.create_invite(req, actor=actor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{invitation_pk}")
async def revoke_invite(
    invitation_pk: str,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    ok = await invite_service.revoke_invite(invitation_pk, actor=actor)
    return {"status": "revoked" if ok else "failed"}

@router.get("/expression-policy")
async def get_expression_policy_snippet(current_user: dict = Depends(get_current_user)):
    return invite_service.get_flow_guide()

@router.post("/install-policy")
async def install_flow_policy(current_user: dict = Depends(get_current_user)):
    try:
        return await invite_service.install_flow_policy()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync")
async def sync_redemptions(current_user: dict = Depends(get_current_user)):
    redeemed = await invite_service.sync_redemptions()
    return {"status": "ok", "redeemed_count": redeemed}
