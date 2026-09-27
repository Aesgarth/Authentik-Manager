from typing import List
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import ApplicationSchema, ProvisionAppGroupRequest, ProvisionAllUnprotectedResponse
from app.services.matrix_service import matrix_service
from app.services.provisioner import provisioner_service

router = APIRouter(prefix="/api/apps", tags=["Applications"])

@router.get("", response_model=List[ApplicationSchema])
async def list_apps(current_user: dict = Depends(get_current_user)):
    matrix = await matrix_service.get_matrix()
    return matrix.apps

@router.post("/provision")
async def provision_app(
    req: ProvisionAppGroupRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    try:
        res = await provisioner_service.provision_app_group(
            app_pk=req.app_pk,
            custom_group_name=req.group_name,
            actor=actor
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/provision-all", response_model=ProvisionAllUnprotectedResponse)
async def provision_all_unprotected(current_user: dict = Depends(get_current_user)):
    actor = current_user.get("username", "Admin")
    res = await provisioner_service.provision_all_unprotected(actor=actor)
    return ProvisionAllUnprotectedResponse(
        provisioned_count=res["provisioned_count"],
        provisioned_apps=res["provisioned_apps"]
    )
