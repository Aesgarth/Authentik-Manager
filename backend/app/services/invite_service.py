import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import aiosqlite
from app.authentik_client import authentik_client
from app.config import settings
from app.database import get_db_path
from app.models import CreateInviteRequest, TrackedInviteSchema
from app.services.audit_service import audit_service

from app.services.whatsapp_service import whatsapp_service

EXPRESSION_POLICY_TEMPLATE = '''# Authentik Enrollment Flow Expression Policy
# Name: Assign Invitation Pre-configured Groups
# Bind this policy to your Enrollment Flow BEFORE the User Write Stage
from authentik.core.models import Group

# Check if prompt_data contains pre-assigned groups from the invitation
if "prompt_data" in request.context and "groups" in request.context.get("prompt_data", {}):
    target_groups = request.context["prompt_data"]["groups"]
    resolved_groups = []
    
    for g_id in target_groups:
        try:
            # Lookup by UUID or Group Name
            group = Group.objects.get(pk=g_id) if len(str(g_id)) == 36 else Group.objects.get(name=g_id)
            resolved_groups.append(group)
        except Group.DoesNotExist:
            ak_logger.warning(f"Group {g_id} not found during invitation enrollment")

    if resolved_groups:
        if "groups" not in request.context["flow_plan"].context:
            request.context["flow_plan"].context["groups"] = []
        request.context["flow_plan"].context["groups"].extend(resolved_groups)

return True
'''

class InviteService:
    async def create_invite(self, req: CreateInviteRequest, actor: str = "Admin") -> TrackedInviteSchema:
        expires_at: Optional[str] = None
        if req.expires_in_days > 0:
            exp_dt = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)
            expires_at = exp_dt.isoformat()

        fixed_data = {
            "groups": req.group_pks,
            "assigned_apps": req.app_names,
        }
        if req.email:
            fixed_data["email"] = req.email.strip()
        if req.phone:
            fixed_data["phone"] = req.phone.strip()

        # 1. Create invitation in Authentik
        # Authentik Invitation 'name' is a SlugField (^[a-zA-Z0-9_-]+$, max 50 chars)
        clean_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', req.name.strip().lower()).strip('-')
        clean_slug = clean_slug[:30].strip('-')
        invite_slug = f"invite-{clean_slug}-{secrets.token_hex(4)}" if clean_slug else f"invite-{secrets.token_hex(4)}"

        authentik_invite = await authentik_client.create_invitation(
            name=invite_slug,
            expires=expires_at,
            fixed_data=fixed_data,
            single_use=req.single_use
        )
        invitation_pk = str(authentik_invite["pk"])

        # 2. Build complete registration URL
        base_url = settings.AUTHENTIK_URL.rstrip("/")
        invite_url = f"{base_url}/if/flow/{settings.DEFAULT_ENROLLMENT_FLOW}/?itoken={invitation_pk}"

        created_at = datetime.now(timezone.utc).isoformat()
        whatsapp_sent = False

        # 3. Optional: Send invitation via WhatsApp
        if req.send_via_whatsapp and req.phone:
            app_list_str = ", ".join(req.app_names) if req.app_names else "Home Services"
            expiry_str = f"in {req.expires_in_days} days" if req.expires_in_days > 0 else "does not expire"
            
            msg = req.custom_message or (
                f"👋 Hi {req.name}!\n\n"
                f"You have been invited to access our private home services ({app_list_str}).\n\n"
                f"👉 Set up your account using your personal invite link:\n{invite_url}\n\n"
                f"🔒 This link is private to you and expires {expiry_str}."
            )
            try:
                await whatsapp_service.send_message(recipient=req.phone, message=msg)
                whatsapp_sent = True
                await audit_service.log(
                    actor=actor,
                    action="SEND_WHATSAPP_INVITE",
                    target_type="INVITATION",
                    target_name=req.name,
                    target_id=invitation_pk,
                    details=f"Sent to {req.phone}",
                    status="SUCCESS"
                )
            except Exception as e:
                await audit_service.log(
                    actor=actor,
                    action="SEND_WHATSAPP_INVITE",
                    target_type="INVITATION",
                    target_name=req.name,
                    target_id=invitation_pk,
                    details=f"Failed to send to {req.phone}: {e}",
                    status="FAILED"
                )

        # 4. Store in local SQLite
        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO tracked_invites (
                    invitation_pk, name, email, phone, whatsapp_sent, expires_at, single_use,
                    assigned_groups, assigned_apps, invite_url, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    invitation_pk,
                    req.name,
                    req.email or "",
                    req.phone or "",
                    1 if whatsapp_sent else 0,
                    expires_at,
                    1 if req.single_use else 0,
                    json.dumps(req.group_pks),
                    json.dumps(req.app_names),
                    invite_url,
                    created_at
                )
            )
            inserted_id = cursor.lastrowid
            await db.commit()

        await audit_service.log(
            actor=actor,
            action="CREATE_INVITE",
            target_type="INVITATION",
            target_name=req.name,
            target_id=invitation_pk,
            details=f"Email: {req.email}, Phone: {req.phone}, Apps: {', '.join(req.app_names)}, Expiry: {expires_at}",
            status="SUCCESS"
        )

        return TrackedInviteSchema(
            id=inserted_id,
            invitation_pk=invitation_pk,
            name=req.name,
            email=req.email,
            phone=req.phone,
            whatsapp_sent=whatsapp_sent,
            expires_at=expires_at,
            single_use=req.single_use,
            assigned_groups=req.group_pks,
            assigned_apps=req.app_names,
            invite_url=invite_url,
            status="pending",
            created_at=created_at
        )

    async def list_invites(self) -> List[TrackedInviteSchema]:
        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tracked_invites ORDER BY id DESC") as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    keys = r.keys()
                    phone = r["phone"] if "phone" in keys and r["phone"] else None
                    whatsapp_sent = bool(r["whatsapp_sent"]) if "whatsapp_sent" in keys else False

                    results.append(TrackedInviteSchema(
                        id=r["id"],
                        invitation_pk=r["invitation_pk"],
                        name=r["name"],
                        email=r["email"] if r["email"] else None,
                        phone=phone,
                        whatsapp_sent=whatsapp_sent,
                        expires_at=r["expires_at"] if r["expires_at"] else None,
                        single_use=bool(r["single_use"]),
                        assigned_groups=json.loads(r["assigned_groups"]),
                        assigned_apps=json.loads(r["assigned_apps"]),
                        invite_url=r["invite_url"],
                        status=r["status"],
                        redeemed_by=r["redeemed_by"],
                        created_at=r["created_at"]
                    ))
                return results

    async def revoke_invite(self, invitation_pk: str, actor: str = "Admin") -> bool:
        try:
            await authentik_client.delete_invitation(invitation_pk)
        except Exception:
            pass

        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE tracked_invites SET status = 'revoked' WHERE invitation_pk = ?",
                (invitation_pk,)
            )
            await db.commit()

        await audit_service.log(
            actor=actor,
            action="REVOKE_INVITE",
            target_type="INVITATION",
            target_name=invitation_pk,
            target_id=invitation_pk,
            status="SUCCESS"
        )
        return True

    async def sync_redemptions(self) -> int:
        """
        Background sync check: Matches newly created users in Authentik against pending invites.
        If a new user matches an invite email (or newly joined), assigns the pre-selected groups via API.
        """
        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tracked_invites WHERE status = 'pending'") as cursor:
                pending = await cursor.fetchall()

        if not pending:
            return 0

        users = await authentik_client.get_users()
        users_by_email = {u.get("email", "").lower(): u for u in users if u.get("email")}
        users_by_username = {u.get("username", "").lower(): u for u in users}

        redeemed_count = 0

        for invite in pending:
            target_email = (invite["email"] or "").lower()
            matched_user = None

            if target_email and target_email in users_by_email:
                matched_user = users_by_email[target_email]

            if matched_user:
                assigned_groups = json.loads(invite["assigned_groups"])
                user_pk = matched_user["pk"]
                username = matched_user.get("username")

                # Assign groups via API
                for g_pk in assigned_groups:
                    try:
                        await authentik_client.add_user_to_group(g_pk, user_pk)
                    except Exception:
                        pass

                # Mark redeemed in DB
                async with aiosqlite.connect(db_path) as db:
                    await db.execute(
                        "UPDATE tracked_invites SET status = 'redeemed', redeemed_by = ? WHERE id = ?",
                        (f"{username} (#{user_pk})", invite["id"])
                    )
                    await db.commit()

                await audit_service.log(
                    actor="AUTO_SYNC_WORKER",
                    action="AUTO_ASSIGN_INVITE_GROUPS",
                    target_type="USER",
                    target_name=username,
                    target_id=str(user_pk),
                    details=f"Assigned {len(assigned_groups)} groups from invite #{invite['id']}",
                    status="SUCCESS"
                )
                redeemed_count += 1

                try:
                    assigned_apps_list = json.loads(invite["assigned_apps"])
                    from app.services.notification_service import notification_service
                    await notification_service.notify_invite_redeemed(
                        user_name=matched_user.get("name") or username,
                        user_email=matched_user.get("email"),
                        assigned_apps=assigned_apps_list
                    )
                except Exception as e:
                    logger.warning(f"Failed to dispatch redemption notification: {e}")

        return redeemed_count

    @staticmethod
    def get_flow_guide() -> Dict[str, str]:
        return {
            "title": "Authentik Native Group Assignment (Optional Zero-Delay Policy)",
            "description": (
                "While Authentik Access Manager includes an automatic background sync worker, "
                "you can also paste this Expression Policy into your Authentik Enrollment Flow. "
                "This ensures groups are applied instantly by Authentik itself during registration."
            ),
            "snippet": EXPRESSION_POLICY_TEMPLATE
        }

invite_service = InviteService()
