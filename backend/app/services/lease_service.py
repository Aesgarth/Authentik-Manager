import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from app.database import (
    save_expiring_grant,
    revoke_expiring_grant,
    get_active_expiring_grants,
    get_due_expiring_grants,
    mark_grant_revoked,
    record_audit_log
)
from app.authentik_client import authentik_client
from app.models import CreateExpiringGrantRequest, RevokeExpiringGrantRequest, ExpiringGrantSchema

logger = logging.getLogger("authentik_manager.lease_service")

class LeaseService:
    async def create_or_update_lease(self, req: CreateExpiringGrantRequest, actor: str = "Admin") -> ExpiringGrantSchema:
        # Determine expiration ISO string
        if req.expires_at:
            expires_at = req.expires_at
        elif req.duration_hours:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)).isoformat()
        else:
            # Default to 7 days if neither supplied
            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        # Add user to group in Authentik
        success = await authentik_client.add_user_to_group(req.group_pk, req.user_pk)
        if not success:
            logger.warning(f"Failed to add user {req.user_pk} to group {req.group_pk} in Authentik")

        # Save record in SQLite
        grant_dict = await save_expiring_grant(
            user_pk=req.user_pk,
            user_name=req.user_name,
            app_pk=req.app_pk,
            app_name=req.app_name,
            group_pk=req.group_pk,
            role=req.role,
            expires_at=expires_at
        )

        await record_audit_log(
            actor=actor,
            action="GRANT_TEMPORARY_ACCESS",
            target_type="EXPIRING_GRANT",
            target_name=f"{req.user_name} on {req.app_name}",
            target_id=str(req.user_pk),
            details=f"Granted {req.role.upper()} role expiring at {expires_at}",
            status="SUCCESS" if success else "WARNING"
        )

        return ExpiringGrantSchema(**grant_dict)

    async def revoke_lease(self, req: RevokeExpiringGrantRequest, actor: str = "Admin") -> bool:
        await revoke_expiring_grant(req.user_pk, req.app_pk, req.group_pk)
        success = await authentik_client.remove_user_from_group(req.group_pk, req.user_pk)

        await record_audit_log(
            actor=actor,
            action="REVOKE_TEMPORARY_ACCESS",
            target_type="EXPIRING_GRANT",
            target_name=f"User #{req.user_pk}",
            target_id=str(req.user_pk),
            details=f"Revoked temporary access on app {req.app_pk}, group {req.group_pk}",
            status="SUCCESS" if success else "WARNING"
        )
        return success

    async def get_active_leases_map(self) -> Dict[str, Dict[str, ExpiringGrantSchema]]:
        active = await get_active_expiring_grants()
        result: Dict[str, Dict[str, ExpiringGrantSchema]] = {}
        for item in active:
            u_pk = str(item["user_pk"])
            a_pk = str(item["app_pk"])
            result.setdefault(u_pk, {})[a_pk] = ExpiringGrantSchema(**item)
        return result

    async def check_and_expire_leases(self) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        due_grants = await get_due_expiring_grants(now_iso)
        expired_count = 0

        for grant in due_grants:
            grant_id = grant["id"]
            u_pk = grant["user_pk"]
            u_name = grant["user_name"]
            a_pk = grant["app_pk"]
            a_name = grant["app_name"]
            g_pk = grant["group_pk"]
            role = grant["role"]

            try:
                # Remove user from group in Authentik
                await authentik_client.remove_user_from_group(g_pk, u_pk)
                # Mark as revoked in database
                await mark_grant_revoked(grant_id)
                expired_count += 1

                await record_audit_log(
                    actor="System Scheduler",
                    action="EXPIRE_TEMPORARY_ACCESS",
                    target_type="EXPIRING_GRANT",
                    target_name=f"{u_name} on {a_name}",
                    target_id=str(u_pk),
                    details=f"Temporary {role.upper()} access grant reached expiration ({grant['expires_at']}) and was revoked automatically.",
                    status="SUCCESS"
                )
                logger.info(f"Automatically expired lease for user {u_name} ({u_pk}) on {a_name}")
            except Exception as e:
                logger.error(f"Failed to auto-expire grant {grant_id} for user {u_pk}: {e}")

        return expired_count

lease_service = LeaseService()
