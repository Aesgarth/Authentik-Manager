import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
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
from app.security import sanitize_csv_cell

import logging

logger = logging.getLogger("authentik_manager.matrix_router")

router = APIRouter(prefix="/api/matrix", tags=["Access Matrix"])

@router.get("", response_model=AccessMatrixResponse)
async def get_access_matrix(current_user: dict = Depends(get_current_user)):
    try:
        from app.services.invite_service import invite_service
        await invite_service.sync_redemptions()
    except Exception as e:
        logger.warning(f"Error syncing invite redemptions in matrix endpoint: {e}")
    try:
        return await matrix_service.get_matrix()
    except Exception as e:
        logger.error(f"Error generating access matrix: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate access matrix: {str(e)}")

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

@router.get("/export/csv")
async def export_matrix_csv(current_user: dict = Depends(get_current_user)):
    matrix = await matrix_service.get_matrix()

    output = io.StringIO()
    writer = csv.writer(output)

    # Headers: Username, Email, Role, Last Login, followed by each Application Name
    app_headers = [sanitize_csv_cell(app.name) for app in matrix.apps]
    writer.writerow([sanitize_csv_cell(h) for h in ["Username", "Email", "Role", "Last Login"]] + app_headers)

    for u in matrix.users:
        user_pk_str = str(u.pk)
        role = "Superuser" if u.is_superuser else "User"
        last_login_str = u.last_login or "Never"

        row = [
            sanitize_csv_cell(u.username),
            sanitize_csv_cell(u.email or ""),
            sanitize_csv_cell(role),
            sanitize_csv_cell(last_login_str),
        ]
        for app in matrix.apps:
            app_pk_str = str(app.pk)
            has_access = matrix.permissions.get(user_pk_str, {}).get(app_pk_str, False)
            is_admin = matrix.admin_permissions.get(user_pk_str, {}).get(app_pk_str, False)
            inherited = matrix.inherited_access.get(user_pk_str, {}).get(app_pk_str, [])
            expiring = matrix.expiring_grants.get(user_pk_str, {}).get(app_pk_str)

            if not has_access:
                val = "No Access"
            elif is_admin:
                val = "Admin"
                if expiring:
                    val += f" (Temporary - Expires: {expiring.expires_at})"
            elif inherited:
                val = f"Inherited ({', '.join(inherited)})"
            elif expiring:
                val = f"Temporary Member (Expires: {expiring.expires_at})"
            else:
                val = "Member"
            row.append(sanitize_csv_cell(val))
        writer.writerow(row)

    csv_content = output.getvalue()
    filename = f"authentik_access_matrix_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

