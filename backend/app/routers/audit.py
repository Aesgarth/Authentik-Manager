from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from app.auth import get_current_user
from app.services.audit_service import audit_service

router = APIRouter(prefix="/api/audit", tags=["Audit Log"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_audit_logs(
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    return await audit_service.list_recent(limit=limit)
