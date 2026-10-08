from typing import List, Dict, Any, Optional
from app.authentik_client import authentik_client
from app.config import settings
from app.services.audit_service import audit_service

class ProvisionerService:
    async def provision_app_group(
        self,
        app_pk: str,
        custom_group_name: Optional[str] = None,
        create_user_group: bool = True,
        create_admin_group: bool = True,
        custom_user_group_name: Optional[str] = None,
        custom_admin_group_name: Optional[str] = None,
        actor: str = "Admin"
    ) -> Dict[str, Any]:
        """
        Provisions dedicated granular access groups (User and/or Admin) and policy bindings
        for an application. Ensures Authentik uses 'any' policy mode so that bindings to
        global groups (like 5AMT admin or 5AMT Home) and granular groups work in harmony.
        """
        apps = await authentik_client.get_applications()
        target_app = next((a for a in apps if str(a["pk"]) == str(app_pk)), None)
        if not target_app:
            raise ValueError(f"Application with PK '{app_pk}' not found.")

        app_name = target_app.get("name", "Unknown App")
        app_slug = target_app.get("slug", "")

        user_group_name = custom_user_group_name or custom_group_name or f"{settings.APP_GROUP_PREFIX}{app_name}"
        admin_group_name = custom_admin_group_name or f"{settings.APP_GROUP_PREFIX}{app_name} Admin"

        groups = await authentik_client.get_groups()
        bindings = await authentik_client.get_policy_bindings(target_pk=app_pk)

        user_group_pk: Optional[str] = None
        user_group_created = False
        user_binding_created = False

        admin_group_pk: Optional[str] = None
        admin_group_created = False
        admin_binding_created = False

        # 1. Provision User Group
        if create_user_group:
            existing_user_group = next(
                (g for g in groups if str(g.get("name") or "").strip().lower() == user_group_name.strip().lower()),
                None
            )
            if existing_user_group:
                user_group_pk = str(existing_user_group.get("pk") or "")
            else:
                new_grp = await authentik_client.create_group(
                    name=user_group_name,
                    attributes={"managed_by": "authentik-access-manager", "app_pk": app_pk, "role": "user"}
                )
                user_group_pk = str(new_grp.get("pk") or "")
                user_group_created = True

            # Policy binding for user group
            existing_user_binding = next(
                (b for b in bindings if str(b.get("group") or "") == user_group_pk),
                None
            )
            if not existing_user_binding:
                await authentik_client.create_policy_binding(
                    target_pk=app_pk,
                    group_pk=user_group_pk,
                    order=10,
                    negate=False
                )
                user_binding_created = True

        # 2. Provision Admin Group
        if create_admin_group:
            existing_admin_group = next(
                (g for g in groups if str(g.get("name") or "").strip().lower() == admin_group_name.strip().lower()),
                None
            )
            if existing_admin_group:
                admin_group_pk = str(existing_admin_group.get("pk") or "")
            else:
                new_grp = await authentik_client.create_group(
                    name=admin_group_name,
                    attributes={"managed_by": "authentik-access-manager", "app_pk": app_pk, "role": "admin"}
                )
                admin_group_pk = str(new_grp.get("pk") or "")
                admin_group_created = True

            # Policy binding for admin group
            existing_admin_binding = next(
                (b for b in bindings if str(b.get("group") or "") == admin_group_pk),
                None
            )
            if not existing_admin_binding:
                await authentik_client.create_policy_binding(
                    target_pk=app_pk,
                    group_pk=admin_group_pk,
                    order=11,
                    negate=False
                )
                admin_binding_created = True

        # 3. Ensure Application Policy Engine Mode is 'any' (OR logic)
        # This guarantees that existing bindings (e.g. 5AMT admin, 5AMT Home) and new app groups all grant access
        if app_slug:
            await authentik_client.set_app_policy_engine_mode(app_slug, "any")

        # 4. Audit Log
        details_list = []
        if user_group_pk:
            details_list.append(f"User Group: {user_group_name} ({user_group_pk})")
        if admin_group_pk:
            details_list.append(f"Admin Group: {admin_group_name} ({admin_group_pk})")

        await audit_service.log(
            actor=actor,
            action="PROVISION_APP_SECURITY",
            target_type="APPLICATION",
            target_name=app_name,
            target_id=app_pk,
            details=", ".join(details_list),
            status="SUCCESS"
        )

        from app.services.matrix_service import matrix_service
        matrix_service.invalidate_cache()

        return {
            "app_pk": app_pk,
            "app_name": app_name,
            "group_pk": user_group_pk or admin_group_pk,
            "group_name": user_group_name if user_group_pk else admin_group_name,
            "group_created": user_group_created or admin_group_created,
            "binding_created": user_binding_created or admin_binding_created,
            "user_group_pk": user_group_pk,
            "user_group_name": user_group_name if create_user_group else None,
            "user_group_created": user_group_created,
            "admin_group_pk": admin_group_pk,
            "admin_group_name": admin_group_name if create_admin_group else None,
            "admin_group_created": admin_group_created,
            "user_binding_created": user_binding_created,
            "admin_binding_created": admin_binding_created,
        }

    async def provision_all_unprotected(
        self,
        create_user_groups: bool = True,
        create_admin_groups: bool = True,
        include_already_secured: bool = True,
        actor: str = "Admin"
    ) -> Dict[str, Any]:
        """
        Provisions missing granular groups across applications.
        If include_already_secured=True, it also provisions granular User & Admin groups
        for applications that already have global bindings (e.g. 5AMT admin or 5AMT Home).
        """
        apps = await authentik_client.get_applications()
        groups = await authentik_client.get_groups()
        bindings = await authentik_client.get_policy_bindings()

        groups_by_name = {str(g.get("name") or "").strip().lower(): g for g in groups if g.get("name")}
        bound_groups_by_app: Dict[str, set] = {}
        for b in bindings:
            target = str(b.get("target") or "")
            grp = str(b.get("group") or "")
            if target and grp:
                bound_groups_by_app.setdefault(target, set()).add(grp)

        provisioned_apps = []
        details = []

        for app in apps:
            app_pk = str(app.get("pk") or "")
            app_name = str(app.get("name") or "Unknown App")
            bound_set = bound_groups_by_app.get(app_pk, set())

            expected_user_name = f"{settings.APP_GROUP_PREFIX}{app_name}".strip().lower()
            expected_admin_name = f"{settings.APP_GROUP_PREFIX}{app_name} Admin".strip().lower()

            has_user_group = False
            if expected_user_name in groups_by_name:
                u_pk = str(groups_by_name[expected_user_name].get("pk") or "")
                if u_pk in bound_set:
                    has_user_group = True

            has_admin_group = False
            if expected_admin_name in groups_by_name:
                a_pk = str(groups_by_name[expected_admin_name].get("pk") or "")
                if a_pk in bound_set:
                    has_admin_group = True

            needs_user = create_user_groups and not has_user_group
            needs_admin = create_admin_groups and not has_admin_group

            # If not including already secured, only provision if app had 0 bindings at all
            if not include_already_secured and len(bound_set) > 0:
                continue

            if needs_user or needs_admin or len(bound_set) == 0:
                res = await self.provision_app_group(
                    app_pk=app_pk,
                    create_user_group=needs_user or (create_user_groups and len(bound_set) == 0),
                    create_admin_group=needs_admin or (create_admin_groups and len(bound_set) == 0),
                    actor=actor
                )
                provisioned_apps.append(app_name)
                details.append(res)

        from app.services.matrix_service import matrix_service
        matrix_service.invalidate_cache()

        return {
            "provisioned_count": len(provisioned_apps),
            "provisioned_apps": provisioned_apps,
            "details": details,
        }

provisioner_service = ProvisionerService()
