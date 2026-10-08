import time
import logging
from typing import List, Dict, Optional, Tuple, Any
from fastapi import HTTPException
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
    CreateExpiringGrantRequest,
)
from app.services.audit_service import audit_service
from app.services.lease_service import lease_service
from app.database import revoke_expiring_grant

logger = logging.getLogger("authentik_manager.matrix_service")

class MatrixService:
    def __init__(self):
        self._cached_matrix: Optional[AccessMatrixResponse] = None
        self._cached_at: float = 0.0

    def invalidate_cache(self):
        self._cached_matrix = None
        self._cached_at = 0.0

    def is_group_allowed_for_app(self, group_pk: str, app_pk: str, matrix: AccessMatrixResponse) -> bool:
        """
        Validates that group_pk is a recognized managed group for app_pk.
        Explicitly prevents assigning arbitrary or global administrative groups (like authentik Admins).
        """
        group_pk_str = str(group_pk)
        app_pk_str = str(app_pk)

        target_app = next((a for a in matrix.apps if str(a.pk) == app_pk_str), None)
        if not target_app:
            return False

        # Disallow if group is superuser or global admin group
        for bg in (target_app.all_bound_groups or []):
            if str(bg.pk) == group_pk_str:
                if bg.is_superuser or bg.name.strip().lower() in ("authentik admins", "admins", "administrator"):
                    return False
                return True

        if target_app.granular_user_group_pk and str(target_app.granular_user_group_pk) == group_pk_str:
            return True
        if target_app.granular_admin_group_pk and str(target_app.granular_admin_group_pk) == group_pk_str:
            return True
        if target_app.bound_group_pk and str(target_app.bound_group_pk) == group_pk_str:
            if target_app.bound_group_name and target_app.bound_group_name.strip().lower() in ("authentik admins", "admins", "administrator"):
                return False
            return True

        return False

    def get_all_managed_group_pks(self, matrix: AccessMatrixResponse) -> set[str]:
        """Returns all valid managed group PKs across all applications, excluding global superuser groups."""
        managed: set[str] = set()
        for a in matrix.apps:
            for bg in (a.all_bound_groups or []):
                if bg.is_superuser or bg.name.strip().lower() in ("authentik admins", "admins", "administrator"):
                    continue
                managed.add(str(bg.pk))
            if a.granular_user_group_pk:
                managed.add(str(a.granular_user_group_pk))
            if a.granular_admin_group_pk:
                managed.add(str(a.granular_admin_group_pk))
            if a.bound_group_pk:
                if not (a.bound_group_name and a.bound_group_name.strip().lower() in ("authentik admins", "admins", "administrator")):
                    managed.add(str(a.bound_group_pk))
        return managed

    async def get_matrix(self, force_refresh: bool = False) -> AccessMatrixResponse:
        if not force_refresh and self._cached_matrix and (time.time() - self._cached_at < 15.0):
            return self._cached_matrix
        apps_raw = await authentik_client.get_applications()
        groups_raw = await authentik_client.get_groups()
        users_raw = await authentik_client.get_users()
        bindings_raw = await authentik_client.get_policy_bindings()

        # Build group lookup maps
        groups_by_pk = {str(g["pk"]): g for g in groups_raw if g.get("pk") is not None}
        groups_by_name = {str(g.get("name") or "").strip().lower(): g for g in groups_raw if g.get("name")}

        # Build app policy binding lookup: target_pk -> list of group_pks
        app_bound_groups: Dict[str, List[str]] = {}
        for b in bindings_raw:
            target = str(b.get("target") or "")
            grp = str(b.get("group") or "")
            if target and grp:
                app_bound_groups.setdefault(target, []).append(grp)

        # Parse applications and associate them with protecting groups
        app_schemas: List[ApplicationSchema] = []
        app_group_map: Dict[str, Optional[str]] = {}
        app_admin_group_map: Dict[str, Optional[str]] = {}

        for app in apps_raw:
            app_pk = str(app.get("pk") or "")
            app_name = str(app.get("name") or "Unnamed App")
            app_slug = str(app.get("slug") or "").strip().lower()
            bound_groups = app_bound_groups.get(app_pk, [])
            bound_group_set = set(bound_groups)

            expected_user_names = [
                f"{settings.APP_GROUP_PREFIX}{app_name}".strip().lower(),
                app_name.strip().lower(),
                f"{app_name} users".strip().lower(),
                f"{app_name}-users".strip().lower(),
            ]
            if app_slug:
                expected_user_names.extend([
                    app_slug,
                    f"{app_slug}-users",
                ])

            expected_admin_names = [
                f"{settings.APP_GROUP_PREFIX}{app_name} admin".strip().lower(),
                f"{app_name} admin".strip().lower(),
                f"{app_name}-admin".strip().lower(),
            ]
            if app_slug:
                expected_admin_names.append(f"{app_slug}-admin")

            # Detect granular user group
            granular_user_group_pk: Optional[str] = None
            granular_user_group_name: Optional[str] = None
            has_granular_user_group = False

            for u_name in expected_user_names:
                if u_name in groups_by_name:
                    u_candidate = groups_by_name[u_name]
                    granular_user_group_pk = str(u_candidate.get("pk") or "")
                    granular_user_group_name = str(u_candidate.get("name") or "")
                    if granular_user_group_pk in bound_group_set:
                        has_granular_user_group = True
                    break

            # If not found by name, fallback to first non-admin bound group
            if not granular_user_group_pk and bound_groups:
                for bg_pk in bound_groups:
                    bg_obj = groups_by_pk.get(bg_pk)
                    bg_name = str(bg_obj.get("name") if bg_obj else bg_pk or "")
                    if not any(admin_kw in bg_name.lower() for admin_kw in ["admin", "administrator"]):
                        granular_user_group_pk = bg_pk
                        granular_user_group_name = bg_name
                        has_granular_user_group = True
                        break

            # Detect granular admin group
            granular_admin_group_pk: Optional[str] = None
            granular_admin_group_name: Optional[str] = None
            has_granular_admin_group = False

            for a_name in expected_admin_names:
                if a_name in groups_by_name:
                    a_candidate = groups_by_name[a_name]
                    granular_admin_group_pk = str(a_candidate.get("pk") or "")
                    granular_admin_group_name = str(a_candidate.get("name") or "")
                    if granular_admin_group_pk in bound_group_set:
                        has_granular_admin_group = True
                    break

            # Build list of all bound group references
            all_bound_groups: List[BoundGroupRef] = []
            for g_pk in bound_groups:
                grp_obj = groups_by_pk.get(g_pk)
                grp_name = str(grp_obj.get("name") if grp_obj else g_pk or "")
                grp_name_clean = grp_name.strip().lower()
                is_u = (g_pk == granular_user_group_pk) or (grp_name_clean in expected_user_names)
                is_a = (g_pk == granular_admin_group_pk) or (grp_name_clean in expected_admin_names) or ("admin" in grp_name_clean)
                is_super = bool(grp_obj.get("is_superuser", False)) if grp_obj else False
                if grp_name_clean in ("authentik admins", "admins", "administrator"):
                    is_super = True
                all_bound_groups.append(BoundGroupRef(
                    pk=g_pk,
                    name=grp_name,
                    is_granular_user=is_u,
                    is_granular_admin=is_a,
                    is_admin_group=is_a,
                    is_superuser=is_super,
                ))

            # Primary bound group to map standard cell clicks to:
            # Prefer granular user group if it exists; otherwise fallback to first bound group
            primary_group_pk: Optional[str] = granular_user_group_pk if has_granular_user_group else (bound_groups[0] if bound_groups else granular_user_group_pk)
            primary_group_name: Optional[str] = None
            if primary_group_pk and primary_group_pk in groups_by_pk:
                primary_group_name = str(groups_by_pk[primary_group_pk].get("name") or "")

            is_protected = len(bound_groups) > 0

            app_group_map[app_pk] = primary_group_pk
            app_admin_group_map[app_pk] = granular_admin_group_pk

            app_schemas.append(ApplicationSchema(
                pk=app_pk,
                name=app_name,
                slug=str(app.get("slug") or ""),
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
                    group_pks.append(str(g.get("pk") or ""))
                else:
                    group_pks.append(str(g or ""))

            u_attrs = u.get("attributes") or {}
            if not isinstance(u_attrs, dict):
                u_attrs = {}

            u_phone = (
                u_attrs.get("phone")
                or u_attrs.get("phone_number")
                or u_attrs.get("phoneNumber")
                or None
            )
            if u_phone:
                u_phone = str(u_phone).strip()

            user_schemas.append(UserSchema(
                pk=u["pk"],
                username=str(u.get("username") or ""),
                name=str(u.get("name") or u.get("username") or ""),
                email=str(u.get("email") or ""),
                phone=u_phone,
                is_active=bool(u.get("is_active", True)),
                is_superuser=bool(u.get("is_superuser", False)),
                groups=group_pks,
                avatar=u.get("avatar"),
                last_login=u.get("last_login"),
                attributes=u_attrs,
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

        expiring_grants = await lease_service.get_active_leases_map()

        resp = AccessMatrixResponse(
            users=user_schemas,
            apps=app_schemas,
            permissions=permissions,
            admin_permissions=admin_permissions,
            inherited_access=inherited_access,
            app_group_map=app_group_map,
            app_admin_group_map=app_admin_group_map,
            expiring_grants=expiring_grants,
        )
        self._cached_matrix = resp
        self._cached_at = time.time()
        return resp

    async def toggle_permission(self, req: TogglePermissionRequest, actor: str = "Admin") -> bool:
        matrix = await self.get_matrix()
        if not self.is_group_allowed_for_app(req.group_pk, req.app_pk, matrix):
            matrix = await self.get_matrix(force_refresh=True)
            if not self.is_group_allowed_for_app(req.group_pk, req.app_pk, matrix):
                logger.warning(
                    f"Unauthorized group toggle rejected: user {req.user_pk}, "
                    f"group {req.group_pk} does not belong to app {req.app_pk}"
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: group '{req.group_pk}' is not a valid managed group for app '{req.app_pk}'."
                )

        if req.grant:
            if req.duration_hours:
                await lease_service.create_or_update_lease(
                    CreateExpiringGrantRequest(
                        user_pk=req.user_pk,
                        user_name=f"User #{req.user_pk}",
                        app_pk=req.app_pk,
                        app_name=f"App {req.app_pk}",
                        group_pk=req.group_pk,
                        role="member",
                        duration_hours=req.duration_hours
                    ),
                    actor=actor
                )
                self.invalidate_cache()
                return True
            else:
                success = await authentik_client.add_user_to_group(req.group_pk, req.user_pk)
                action_desc = "GRANT_APP_ACCESS"
        else:
            # Revoke in Authentik FIRST, only remove SQLite grant if Authentik succeeds
            success = await authentik_client.remove_user_from_group(req.group_pk, req.user_pk)
            if success:
                await revoke_expiring_grant(req.user_pk, req.app_pk, req.group_pk)
            action_desc = "REVOKE_APP_ACCESS"

        self.invalidate_cache()

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
