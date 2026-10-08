import logging
from typing import List, Dict, Any, Optional
from app.database import (
    get_access_templates,
    get_access_template,
    save_access_template,
    update_access_template,
    delete_access_template,
    record_audit_log
)
from app.authentik_client import authentik_client
from app.services.matrix_service import matrix_service
from app.services.lease_service import lease_service
from app.models import (
    AccessTemplateSchema,
    CreateAccessTemplateRequest,
    UpdateAccessTemplateRequest,
    ApplyAccessTemplateRequest,
    CreateExpiringGrantRequest
)

logger = logging.getLogger("authentik_manager.template_service")

class TemplateService:
    async def list_templates(self) -> List[AccessTemplateSchema]:
        rows = await get_access_templates()
        return [AccessTemplateSchema(**r) for r in rows]

    async def create_template(self, req: CreateAccessTemplateRequest) -> AccessTemplateSchema:
        saved = await save_access_template(
            name=req.name,
            description=req.description,
            icon=req.icon or "shield",
            assignments=req.assignments
        )
        await record_audit_log(
            actor="Admin",
            action="CREATE_ACCESS_TEMPLATE",
            target_type="ACCESS_TEMPLATE",
            target_name=req.name,
            target_id=str(saved["id"]),
            details=f"Defined template with {len(req.assignments)} application assignments",
            status="SUCCESS"
        )
        return AccessTemplateSchema(**saved)

    async def update_template(self, template_id: int, req: UpdateAccessTemplateRequest) -> AccessTemplateSchema:
        updated = await update_access_template(
            template_id=template_id,
            name=req.name,
            description=req.description,
            icon=req.icon,
            assignments=req.assignments
        )
        if not updated:
            raise ValueError(f"Template #{template_id} not found")

        await record_audit_log(
            actor="Admin",
            action="UPDATE_ACCESS_TEMPLATE",
            target_type="ACCESS_TEMPLATE",
            target_name=updated["name"],
            target_id=str(template_id),
            details=f"Updated preset '{updated['name']}' with {len(updated['assignments'])} assignments",
            status="SUCCESS"
        )
        return AccessTemplateSchema(**updated)

    async def delete_template(self, template_id: int) -> bool:
        t = await get_access_template(template_id)
        name = t["name"] if t else f"#{template_id}"
        deleted = await delete_access_template(template_id)
        if deleted:
            await record_audit_log(
                actor="Admin",
                action="DELETE_ACCESS_TEMPLATE",
                target_type="ACCESS_TEMPLATE",
                target_name=name,
                target_id=str(template_id),
                status="SUCCESS"
            )
        return deleted

    async def apply_template(self, req: ApplyAccessTemplateRequest, actor: str = "Admin") -> Dict[str, Any]:
        template = await get_access_template(req.template_id)
        if not template:
            raise ValueError(f"Template #{req.template_id} not found")

        # Fetch current matrix to resolve app groups
        matrix = await matrix_service.get_matrix()
        apps_by_pk = {a.pk: a for a in matrix.apps}
        apps_by_slug = {str(a.slug or "").strip().lower(): a for a in matrix.apps if a.slug}

        applied_apps: List[str] = []
        assignments: Dict[str, str] = template["assignments"]

        # Support wildcard "*" in templates (e.g. apply to all apps)
        is_wildcard = "*" in assignments
        wildcard_role = assignments.get("*", "member")

        target_app_roles: Dict[str, str] = {}
        if is_wildcard:
            for app in matrix.apps:
                target_app_roles[app.pk] = wildcard_role
        
        # Override / merge specific app assignments
        for key, role in assignments.items():
            if key == "*":
                continue
            if key in apps_by_pk:
                target_app_roles[key] = role
            elif key.strip().lower() in apps_by_slug:
                target_app_roles[apps_by_slug[key.strip().lower()].pk] = role

        for app_pk, target_role in target_app_roles.items():
            app = apps_by_pk.get(app_pk)
            if not app:
                continue

            user_group = app.granular_user_group_pk or app.bound_group_pk
            admin_group = app.granular_admin_group_pk

            if target_role == "admin" and admin_group:
                await authentik_client.add_user_to_group(admin_group, req.user_pk)
                if user_group:
                    await authentik_client.add_user_to_group(user_group, req.user_pk)
                
                if req.duration_hours:
                    await lease_service.create_or_update_lease(CreateExpiringGrantRequest(
                        user_pk=req.user_pk,
                        user_name=req.user_name,
                        app_pk=app.pk,
                        app_name=app.name,
                        group_pk=admin_group,
                        role="admin",
                        duration_hours=req.duration_hours
                    ), actor=actor)

                applied_apps.append(f"{app.name} [Admin]")

            elif (target_role == "member" or target_role == "user") and user_group:
                await authentik_client.add_user_to_group(user_group, req.user_pk)
                if req.duration_hours:
                    await lease_service.create_or_update_lease(CreateExpiringGrantRequest(
                        user_pk=req.user_pk,
                        user_name=req.user_name,
                        app_pk=app.pk,
                        app_name=app.name,
                        group_pk=user_group,
                        role="member",
                        duration_hours=req.duration_hours
                    ), actor=actor)

                applied_apps.append(app.name)

        await record_audit_log(
            actor=actor,
            action="APPLY_ACCESS_TEMPLATE",
            target_type="USER",
            target_name=req.user_name,
            target_id=str(req.user_pk),
            details=f"Applied template '{template['name']}' ({len(applied_apps)} services assigned" + (f", expiring in {req.duration_hours}h" if req.duration_hours else "") + ")",
            status="SUCCESS"
        )

        matrix_service.invalidate_cache()

        return {
            "template_name": template["name"],
            "user_pk": req.user_pk,
            "user_name": req.user_name,
            "applied_count": len(applied_apps),
            "applied_apps": applied_apps,
            "expires_in_hours": req.duration_hours
        }

template_service = TemplateService()
