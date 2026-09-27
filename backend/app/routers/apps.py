from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import (
    ApplicationSchema,
    ProvisionAppGroupRequest,
    ProvisionAllRequest,
    ProvisionAllUnprotectedResponse,
)
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
            create_user_group=req.create_user_group,
            create_admin_group=req.create_admin_group,
            custom_user_group_name=req.custom_user_group_name,
            custom_admin_group_name=req.custom_admin_group_name,
            actor=actor
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/provision-all", response_model=ProvisionAllUnprotectedResponse)
async def provision_all_unprotected(
    req: Optional[ProvisionAllRequest] = None,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    create_user_groups = req.create_user_groups if req else True
    create_admin_groups = req.create_admin_groups if req else True
    include_already_secured = req.include_already_secured if req else True

    res = await provisioner_service.provision_all_unprotected(
        create_user_groups=create_user_groups,
        create_admin_groups=create_admin_groups,
        include_already_secured=include_already_secured,
        actor=actor
    )
    return ProvisionAllUnprotectedResponse(
        provisioned_count=res["provisioned_count"],
        provisioned_apps=res["provisioned_apps"],
        details=res.get("details", [])
    )
