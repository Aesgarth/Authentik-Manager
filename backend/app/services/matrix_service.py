from typing import List, Dict, Optional, Tuple, Any
from app.authentik_client import authentik_client
from app.config import settings
from app.models import (
    UserSchema,
    GroupSchema,
    ApplicationSchema,
    AccessMatrixResponse,
    TogglePermissionRequest,
    BulkToggleRequest,
)
from app.services.audit_service import audit_service

class MatrixService:
    async def get_matrix(self) -> AccessMatrixResponse:
        apps_raw = await authentik_client.get_applications()
        groups_raw = await authentik_client.get_groups()
        users_raw = await authentik_client.get_users()
        bindings_raw = await authentik_client.get_policy_bindings()

        # Build group lookup map: group_pk -> group_dict
        groups_by_pk = {g["pk"]: g for g in groups_raw}
        groups_by_name = {g["name"].lower(): g for g in groups_raw}

        # Build app policy binding lookup: target_pk -> list of group_pks
        app_bound_groups: Dict[str, List[str]] = {}
        for b in bindings_raw:
            target = b.get("target")
            grp = b.get("group")
            if target and grp:
                app_bound_groups.setdefault(target, []).append(grp)

        # Parse applications and associate them with protecting groups
        app_schemas: List[ApplicationSchema] = []
        app_group_map: Dict[str, Optional[str]] = {}

        for app in apps_raw:
            app_pk = str(app["pk"])
            app_name = app.get("name", "Unnamed App")
            bound_groups = app_bound_groups.get(app_pk, [])
            
            bound_group_pk: Optional[str] = None
            bound_group_name: Optional[str] = None
            is_protected = False

            if bound_groups:
                # App has explicit policy bindings to group(s)
                bound_group_pk = bound_groups[0]
                is_protected = True
                if bound_group_pk in groups_by_pk:
                    bound_group_name = groups_by_pk[bound_group_pk]["name"]
            else:
                # Check if group exists following naming convention even if not yet bound
                expected_group_name = f"{settings.APP_GROUP_PREFIX}{app_name}".lower()
                if expected_group_name in groups_by_name:
                    matching_group = groups_by_name[expected_group_name]
                    bound_group_pk = matching_group["pk"]
                    bound_group_name = matching_group["name"]
                    # Still marked as unprotected because no policy binding is attached!
                    is_protected = False

            app_group_map[app_pk] = bound_group_pk

            app_schemas.append(ApplicationSchema(
                pk=app_pk,
                name=app_name,
                slug=app.get("slug", ""),
                group=app.get("group"),
                meta_icon=app.get("meta_icon"),
                meta_description=app.get("meta_description"),
                launch_url=app.get("launch_url"),
                is_protected=is_protected,
                bound_group_pk=bound_group_pk,
                bound_group_name=bound_group_name,
            ))

        # Parse users
        user_schemas: List[UserSchema] = []
        for u in users_raw:
            # Handle groups: either list of PKs or list of objects
            raw_groups = u.get("groups", [])
            group_pks = []
            for g in raw_groups:
                if isinstance(g, dict):
                    group_pks.append(g.get("pk"))
                else:
                    group_pks.append(str(g))

            user_schemas.append(UserSchema(
                pk=u["pk"],
                username=u.get("username", ""),
                name=u.get("name") or u.get("username", ""),
                email=u.get("email", ""),
                is_active=u.get("is_active", True),
                is_superuser=u.get("is_superuser", False),
                groups=group_pks,
                avatar=u.get("avatar"),
                last_login=u.get("last_login"),
            ))

        # Compute permissions matrix: permissions[user_pk][app_pk] -> bool
        permissions: Dict[str, Dict[str, bool]] = {}

        for user in user_schemas:
            u_pk_str = str(user.pk)
            permissions[u_pk_str] = {}
            user_group_set = set(user.groups)

            for app in app_schemas:
                app_pk_str = app.pk
                target_group_pk = app_group_map.get(app_pk_str)

                if user.is_superuser:
                    # Superusers inherently have access
                    permissions[u_pk_str][app_pk_str] = True
                elif target_group_pk and target_group_pk in user_group_set:
                    permissions[u_pk_str][app_pk_str] = True
                else:
                    permissions[u_pk_str][app_pk_str] = False

        return AccessMatrixResponse(
            users=user_schemas,
            apps=app_schemas,
            permissions=permissions,
            app_group_map=app_group_map,
        )

    async def toggle_permission(self, req: TogglePermissionRequest, actor: str = "Admin") -> bool:
        if req.grant:
            success = await authentik_client.add_user_to_group(req.group_pk, req.user_pk)
            action_desc = "GRANT_APP_ACCESS"
        else:
            success = await authentik_client.remove_user_from_group(req.group_pk, req.user_pk)
            action_desc = "REVOKE_APP_ACCESS"

        await audit_service.log(
            actor=actor,
            action=action_desc,
            target_type="USER_PERMISSION",
            target_name=f"User #{req.user_pk}",
            target_id=str(req.user_pk),
            details=f"App: {req.app_pk}, Group: {req.group_pk}, Granted: {req.grant}",
            status="SUCCESS" if success else "FAILED"
        )
        return success

    async def bulk_toggle_permissions(self, req: BulkToggleRequest, actor: str = "Admin") -> Dict[str, Any]:
        succeeded = 0
        failed = 0
        for change in req.changes:
            try:
                ok = await self.toggle_permission(change, actor=actor)
                if ok:
                    succeeded += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {"succeeded": succeeded, "failed": failed, "total": len(req.changes)}

matrix_service = MatrixService()
