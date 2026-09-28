from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import (
    AccessMatrixResponse,
    TogglePermissionRequest,
    BulkToggleRequest,
    CreateExpiringGrantRequest,
    RevokeExpiringGrantRequest,
    ExpiringGrantSchema,
)
from app.services.matrix_service import matrix_service
from app.services.lease_service import lease_service

router = APIRouter(prefix="/api/matrix", tags=["Access Matrix"])

@router.get("", response_model=AccessMatrixResponse)
async def get_access_matrix(current_user: dict = Depends(get_current_user)):
    return await matrix_service.get_matrix()

@router.post("/toggle")
async def toggle_permission(
    req: TogglePermissionRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    success = await matrix_service.toggle_permission(req, actor=actor)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update group membership in Authentik")
    return {"status": "success", "granted": req.grant}

@router.post("/bulk-toggle")
async def bulk_toggle_permissions(
    req: BulkToggleRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    result = await matrix_service.bulk_toggle_permissions(req, actor=actor)
    return result

@router.post("/lease", response_model=ExpiringGrantSchema)
async def create_or_update_lease(
    req: CreateExpiringGrantRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    try:
        return await lease_service.create_or_update_lease(req, actor=actor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/lease")
async def revoke_lease(
    req: RevokeExpiringGrantRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    success = await lease_service.revoke_lease(req, actor=actor)
    return {"status": "success", "revoked": success}
