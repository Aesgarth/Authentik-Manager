from typing import List, Dict, Any, Optional
from app.authentik_client import authentik_client
from app.config import settings
from app.services.audit_service import audit_service

class ProvisionerService:
    async def provision_app_group(
        self,
        app_pk: str,
        custom_group_name: Optional[str] = None,
        actor: str = "Admin"
    ) -> Dict[str, Any]:
        """
        Ensures a dedicated access group and policy binding exist for an application.
        Default Deny enforcement: Once bound, only group members can access the app.
        """
        # Fetch application
        apps = await authentik_client.get_applications()
        target_app = next((a for a in apps if str(a["pk"]) == str(app_pk)), None)
        if not target_app:
            raise ValueError(f"Application with PK '{app_pk}' not found.")

        app_name = target_app.get("name", "Unknown App")
        group_name = custom_group_name or f"{settings.APP_GROUP_PREFIX}{app_name}"

        # 1. Check or create the access group
        groups = await authentik_client.get_groups()
        existing_group = next(
            (g for g in groups if g["name"].strip().lower() == group_name.strip().lower()),
            None
        )

        if existing_group:
            group_pk = str(existing_group["pk"])
            group_created = False
        else:
            new_group = await authentik_client.create_group(
                name=group_name,
                attributes={"managed_by": "authentik-access-manager", "app_pk": app_pk}
            )
            group_pk = str(new_group["pk"])
            group_created = True

        # 2. Check or create the policy binding on the application
        bindings = await authentik_client.get_policy_bindings(target_pk=app_pk)
        existing_binding = next(
            (b for b in bindings if str(b.get("group")) == group_pk),
            None
        )

        if existing_binding:
            binding_pk = str(existing_binding["pk"])
            binding_created = False
        else:
            new_binding = await authentik_client.create_policy_binding(
                target_pk=app_pk,
                group_pk=group_pk,
                order=0,
                negate=False
            )
            binding_pk = str(new_binding["pk"])
            binding_created = True

        # 3. Add admin/superuser user to the group to prevent lockout
        users = await authentik_client.get_users()
        superusers = [u for u in users if u.get("is_superuser")]
        for su in superusers:
            try:
                await authentik_client.add_user_to_group(group_pk, su["pk"])
            except Exception:
                pass

        await audit_service.log(
            actor=actor,
            action="PROVISION_APP_SECURITY",
            target_type="APPLICATION",
            target_name=app_name,
            target_id=app_pk,
            details=f"Group: {group_name} ({group_pk}), Binding: {binding_pk}",
            status="SUCCESS"
        )

        return {
            "app_pk": app_pk,
            "app_name": app_name,
            "group_pk": group_pk,
            "group_name": group_name,
            "group_created": group_created,
            "binding_created": binding_created,
        }

    async def provision_all_unprotected(self, actor: str = "Admin") -> Dict[str, Any]:
        """
        Scans all applications and provisions groups + bindings for every application
        that currently lacks policy bindings (i.e., currently wide open).
        """
        apps = await authentik_client.get_applications()
        bindings = await authentik_client.get_policy_bindings()

        bound_targets = {str(b.get("target")) for b in bindings if b.get("target")}

        provisioned = []
        for app in apps:
            app_pk = str(app["pk"])
            if app_pk not in bound_targets:
                res = await self.provision_app_group(app_pk=app_pk, actor=actor)
                provisioned.append(res["app_name"])

        return {
            "provisioned_count": len(provisioned),
            "provisioned_apps": provisioned
        }

provisioner_service = ProvisionerService()
