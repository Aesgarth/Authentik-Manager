import aiosqlite
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import UserSchema, UpdateUserPhoneRequest
from app.services.matrix_service import matrix_service
from app.authentik_client import authentik_client
from app.services.audit_service import audit_service
from app.database import get_db_path

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("", response_model=List[UserSchema])
async def list_users(current_user: dict = Depends(get_current_user)):
    matrix = await matrix_service.get_matrix()
    return matrix.users

@router.post("/{user_pk}/toggle-active")
async def toggle_user_active(user_pk: int, current_user: dict = Depends(get_current_user)):
    actor = current_user.get("username", "Admin")
    # In live mode or demo mode, update user
    users = await authentik_client.get_users()
    target_user = next((u for u in users if u["pk"] == user_pk), None)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    new_state = not target_user.get("is_active", True)
    
    if authentik_client.demo_mode:
        target_user["is_active"] = new_state
    else:
        await authentik_client._request(
            "PATCH",
            f"/api/v3/core/users/{user_pk}/",
            json={"is_active": new_state}
        )

    await audit_service.log(
        actor=actor,
        action="TOGGLE_USER_ACTIVE",
        target_type="USER",
        target_name=target_user.get("username", f"User #{user_pk}"),
        target_id=str(user_pk),
        details=f"Set is_active to {new_state}",
        status="SUCCESS"
    )

    matrix_service.invalidate_cache()
    return {"user_pk": user_pk, "is_active": new_state}

@router.patch("/{user_pk}/phone")
async def update_user_phone(
    user_pk: int,
    req: UpdateUserPhoneRequest,
    current_user: dict = Depends(get_current_user)
):
    actor = current_user.get("username", "Admin")
    phone_clean = req.phone.strip() if req.phone else ""

    # 1. Verify user exists
    user = await authentik_client.get_user(user_pk)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Update Authentik user attributes
    new_attrs = {
        "phone": phone_clean,
        "phone_number": phone_clean,
        "phoneNumber": phone_clean
    }
    await authentik_client.update_user_attributes(user_pk, new_attrs)

    # 2. Also update tracked_invites for this user if an invite was redeemed by them
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE tracked_invites 
            SET phone = ? 
            WHERE redeemed_by LIKE ? OR redeemed_by LIKE ?
            """,
            (phone_clean, f"%#{user_pk}%", f"%User #{user_pk}%")
        )
        await db.commit()

    # 3. Audit log
    await audit_service.log(
        actor=actor,
        action="UPDATE_USER_PHONE",
        target_type="USER",
        target_name=f"User #{user_pk}",
        target_id=str(user_pk),
        details=f"Updated phone number to '{phone_clean}'" if phone_clean else "Cleared phone number",
        status="SUCCESS"
    )

    matrix_service.invalidate_cache()
    return {"user_pk": user_pk, "phone": phone_clean}
