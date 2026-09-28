from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import SettingsResponse, UpdateSettingsRequest, TestConnectionRequest, TestConnectionResponse
from app.services.settings_service import settings_service

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
