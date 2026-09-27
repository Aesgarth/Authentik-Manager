from typing import List, Dict, Any, Optional
from app.database import record_audit_log, get_audit_logs

class AuditService:
    @staticmethod
    async def log(
        actor: str,
        action: str,
        target_type: str,
        target_name: str,
        target_id: Optional[str] = None,
        details: Optional[str] = None,
        status: str = "SUCCESS"
    ):
        await record_audit_log(
            actor=actor,
            action=action,
            target_type=target_type,
            target_name=target_name,
            target_id=target_id,
            details=details,
            status=status
        )

    @staticmethod
    async def list_recent(limit: int = 100) -> List[Dict[str, Any]]:
        return await get_audit_logs(limit)

audit_service = AuditService()
