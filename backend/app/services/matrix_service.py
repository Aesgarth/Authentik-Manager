from typing import List, Dict, Optional, Tuple, Any
from app.authentik_client import authentik_client
from app.config import settings
from app.models import (
    UserSchema,
    GroupSchema,
    ApplicationSchema,
    BoundGroupRef,
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

        # Build group lookup maps
        groups_by_pk = {str(g["pk"]): g for g in groups_raw}
        groups_by_name = {g["name"].strip().lower(): g for g in groups_raw}

        # Build app policy binding lookup: target_pk -> list of group_pks
        app_bound_groups: Dict[str, List[str]] = {}
        for b in bindings_raw:
            target = str(b.get("target", ""))
            grp = str(b.get("group", ""))
            if target and grp:
                app_bound_groups.setdefault(target, []).append(grp)

        # Parse applications and associate them with protecting groups
        app_schemas: List[ApplicationSchema] = []
        app_group_map: Dict[str, Optional[str]] = {}
        app_admin_group_map: Dict[str, Optional[str]] = {}

        for app in apps_raw:
            app_pk = str(app["pk"])
            app_name = app.get("name", "Unnamed App")
            bound_groups = app_bound_groups.get(app_pk, [])
            bound_group_set = set(bound_groups)

            expected_user_name = f"{settings.APP_GROUP_PREFIX}{app_name}".strip().lower()
            expected_admin_names = [
                f"{settings.APP_GROUP_PREFIX}{app_name} admin".strip().lower(),
                f"{app_name} admin".strip().lower(),
            ]

            # Detect granular user group
            granular_user_group_pk: Optional[str] = None
            granular_user_group_name: Optional[str] = None
            has_granular_user_group = False

            if expected_user_name in groups_by_name:
                u_candidate = groups_by_name[expected_user_name]
                granular_user_group_pk = str(u_candidate["pk"])
                granular_user_group_name = u_candidate["name"]
                if granular_user_group_pk in bound_group_set:
                    has_granular_user_group = True

            # Detect granular admin group
            granular_admin_group_pk: Optional[str] = None
            granular_admin_group_name: Optional[str] = None
            has_granular_admin_group = False

            for a_name in expected_admin_names:
                if a_name in groups_by_name:
                    a_candidate = groups_by_name[a_name]
                    granular_admin_group_pk = str(a_candidate["pk"])
                    granular_admin_group_name = a_candidate["name"]
                    if granular_admin_group_pk in bound_group_set:
                        has_granular_admin_group = True
                    break

            # Build list of all bound group references
            all_bound_groups: List[BoundGroupRef] = []
            for g_pk in bound_groups:
                grp_obj = groups_by_pk.get(g_pk)
                grp_name = grp_obj["name"] if grp_obj else g_pk
                is_u = (g_pk == granular_user_group_pk) or (grp_name.strip().lower() == expected_user_name)
                is_a = (g_pk == granular_admin_group_pk) or (grp_name.strip().lower() in expected_admin_names) or ("admin" in grp_name.strip().lower())
                all_bound_groups.append(BoundGroupRef(
                    pk=g_pk,
                    name=grp_name,
                    is_granular_user=is_u,
                    is_granular_admin=is_a,
                    is_admin_group=is_a,
                ))

            # Primary bound group to map standard cell clicks to:
            # Prefer granular user group if it exists; otherwise fallback to first bound group
            primary_group_pk: Optional[str] = granular_user_group_pk if has_granular_user_group else (bound_groups[0] if bound_groups else granular_user_group_pk)
            primary_group_name: Optional[str] = None
            if primary_group_pk and primary_group_pk in groups_by_pk:
                primary_group_name = groups_by_pk[primary_group_pk]["name"]

            is_protected = len(bound_groups) > 0

            app_group_map[app_pk] = primary_group_pk
            app_admin_group_map[app_pk] = granular_admin_group_pk

            app_schemas.append(ApplicationSchema(
                pk=app_pk,
                name=app_name,
                slug=app.get("slug", ""),
                group=app.get("group"),
                meta_icon=app.get("meta_icon"),
                meta_description=app.get("meta_description"),
                launch_url=app.get("launch_url"),
                is_protected=is_protected,
                bound_group_pk=primary_group_pk,
                bound_group_name=primary_group_name,
                granular_user_group_pk=granular_user_group_pk,
                granular_user_group_name=granular_user_group_name,
                granular_admin_group_pk=granular_admin_group_pk,
                granular_admin_group_name=granular_admin_group_name,
                has_granular_user_group=has_granular_user_group,
                has_granular_admin_group=has_granular_admin_group,
                all_bound_groups=all_bound_groups,
            ))

        # Parse users
        user_schemas: List[UserSchema] = []
        for u in users_raw:
            raw_groups = u.get("groups", [])
            group_pks = []
            for g in raw_groups:
                if isinstance(g, dict):
                    group_pks.append(str(g.get("pk")))
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

        # Compute permissions matrices:
        # permissions[u_pk][app_pk] -> has access (direct, admin, or inherited)
        # admin_permissions[u_pk][app_pk] -> has admin role (granular admin group or superuser)
        # inherited_access[u_pk][app_pk] -> list of inherited bound group names (e.g. ["5AMT Home"])
        permissions: Dict[str, Dict[str, bool]] = {}
        admin_permissions: Dict[str, Dict[str, bool]] = {}
        inherited_access: Dict[str, Dict[str, List[str]]] = {}

        for user in user_schemas:
            u_pk_str = str(user.pk)
            permissions[u_pk_str] = {}
            admin_permissions[u_pk_str] = {}
            inherited_access[u_pk_str] = {}
            user_group_set = set(user.groups)

            for app in app_schemas:
                app_pk_str = app.pk

                if user.is_superuser:
                    permissions[u_pk_str][app_pk_str] = True
                    admin_permissions[u_pk_str][app_pk_str] = True
                    inherited_access[u_pk_str][app_pk_str] = ["Superuser"]
                    continue

                # Granular user access
                has_direct_user = bool(
                    app.granular_user_group_pk and
                    app.granular_user_group_pk in user_group_set
                )

                # Granular admin access
                has_direct_admin = bool(
                    app.granular_admin_group_pk and
                    app.granular_admin_group_pk in user_group_set
                )

                # Inherited access via global or broad groups (e.g. 5AMT Home, 5AMT admin)
                inherited = []
                for bg in app.all_bound_groups:
                    if bg.pk in user_group_set and bg.pk != app.granular_user_group_pk and bg.pk != app.granular_admin_group_pk:
                        inherited.append(bg.name)

                # Overall access
                has_any_access = has_direct_user or has_direct_admin or (len(inherited) > 0)
                permissions[u_pk_str][app_pk_str] = has_any_access
                admin_permissions[u_pk_str][app_pk_str] = has_direct_admin
                inherited_access[u_pk_str][app_pk_str] = inherited

        return AccessMatrixResponse(
            users=user_schemas,
            apps=app_schemas,
            permissions=permissions,
            admin_permissions=admin_permissions,
            inherited_access=inherited_access,
            app_group_map=app_group_map,
            app_admin_group_map=app_admin_group_map,
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
