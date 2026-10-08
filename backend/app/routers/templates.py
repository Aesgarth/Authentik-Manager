from typing import List, Dict, Any
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import (
    AccessTemplateSchema,
    CreateAccessTemplateRequest,
    UpdateAccessTemplateRequest,
    ApplyAccessTemplateRequest
)
from app.services.template_service import template_service

logger = logging.getLogger("authentik_manager.templates")

router = APIRouter(prefix="/api/templates", tags=["Access Templates"])

@router.get("", response_model=List[AccessTemplateSchema])
async def list_access_templates(current_user: dict = Depends(get_current_user)):
    return await template_service.list_templates()

@router.post("", response_model=AccessTemplateSchema)
async def create_access_template(
    req: CreateAccessTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        return await template_service.create_template(req)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{template_id}", response_model=AccessTemplateSchema)
async def update_access_template(
    template_id: int,
    req: UpdateAccessTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        return await template_service.update_template(template_id, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{template_id}")
async def delete_access_template(
    template_id: int,
    current_user: dict = Depends(get_current_user)
):
    success = await template_service.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "success", "deleted": True}

@router.post("/{template_id}/apply")
async def apply_access_template(
    template_id: int,
    req: ApplyAccessTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    # Ensure template_id matches
    req.template_id = template_id
    try:
        result = await template_service.apply_template(req, actor=actor)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error applying template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
