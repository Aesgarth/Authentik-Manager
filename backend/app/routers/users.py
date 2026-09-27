from typing import List
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.models import UserSchema
from app.services.matrix_service import matrix_service
from app.authentik_client import authentik_client
from app.services.audit_service import audit_service

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

    return {"user_pk": user_pk, "is_active": new_state}
