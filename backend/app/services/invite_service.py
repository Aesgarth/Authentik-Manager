import asyncio
import json
import logging
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

logger = logging.getLogger("authentik_manager.invite_service")

EXPRESSION_POLICY_TEMPLATE = '''# Authentik Enrollment Flow Expression Policy
# Name: Assign Invitation Pre-configured Groups
# Bind this policy to your Enrollment Flow BEFORE or ON the User Write Stage
from authentik.core.models import Group

# 1. Extract pre-assigned groups from prompt_data (where Invitation Stage injects fixed_data)
prompt_data = (
    getattr(request, "context", {}).get("prompt_data", {})
    if hasattr(request, "context") and isinstance(request.context, dict)
    else context.get("prompt_data", {})
)

target_groups = []
if isinstance(prompt_data, dict):
    target_groups = (
        prompt_data.get("groups_to_add")
        or prompt_data.get("groups")
        or prompt_data.get("group_names")
        or []
    )

# Fallback: check flow_plan context
if not target_groups and hasattr(request, "context") and isinstance(request.context, dict) and "flow_plan" in request.context:
    fp_ctx = getattr(request.context["flow_plan"], "context", {})
    if isinstance(fp_ctx, dict):
        fp_prompt = fp_ctx.get("prompt_data", {})
        if isinstance(fp_prompt, dict):
            target_groups = (
                fp_prompt.get("groups_to_add")
                or fp_prompt.get("groups")
                or fp_prompt.get("group_names")
                or []
            )

# Fallback: check direct invitation object if present in context
if not target_groups:
    inv = context.get("invitation") or (getattr(request, "context", {}).get("invitation") if hasattr(request, "context") else None)
    if inv:
        fd = getattr(inv, "fixed_data", None) or (inv.get("fixed_data", {}) if isinstance(inv, dict) else {})
        if isinstance(fd, dict):
            target_groups = fd.get("groups_to_add") or fd.get("groups") or fd.get("group_names") or []

if isinstance(target_groups, str):
    target_groups = [target_groups]

if target_groups:
    resolved_groups = []
    for g_id in target_groups:
        g_str = str(g_id).strip()
        if not g_str:
            continue
        try:
            # Lookup by UUID (length 36) or by Group Name
            if len(g_str) == 36:
                grp = Group.objects.get(pk=g_str)
            else:
                grp = Group.objects.get(name=g_str)
            if grp not in resolved_groups:
                resolved_groups.append(grp)
        except Group.DoesNotExist:
            try:
                grp = Group.objects.get(name=g_str)
                if grp not in resolved_groups:
                    resolved_groups.append(grp)
            except Group.DoesNotExist:
                ak_logger.warning(f"Group {g_str} not found during invitation enrollment")
        except Exception as e:
            ak_logger.warning(f"Error resolving group {g_str}: {e}")

    if resolved_groups:
        ak_logger.info(f"Assigning {len(resolved_groups)} invitation groups: {[g.name for g in resolved_groups]}")

        # Method A: Set on flow_plan context (consumed by User Write Stage)
        flow_plan = (
            getattr(request, "context", {}).get("flow_plan")
            if hasattr(request, "context") and isinstance(request.context, dict)
            else context.get("flow_plan")
        )
        if flow_plan and hasattr(flow_plan, "context"):
            if "groups" not in flow_plan.context or not isinstance(flow_plan.context["groups"], list):
                flow_plan.context["groups"] = []
            for rg in resolved_groups:
                if rg not in flow_plan.context["groups"]:
                    flow_plan.context["groups"].append(rg)
        elif isinstance(flow_plan, dict) and "context" in flow_plan:
            if "groups" not in flow_plan["context"] or not isinstance(flow_plan["context"]["groups"], list):
                flow_plan["context"]["groups"] = []
            for rg in resolved_groups:
                if rg not in flow_plan["context"]["groups"]:
                    flow_plan["context"]["groups"].append(rg)

        # Method B: Direct assignment if pending_user is already saved to database
        pending_user = context.get("pending_user") or (getattr(request, "context", {}).get("pending_user") if hasattr(request, "context") else None)
        if pending_user and getattr(pending_user, "pk", None):
            for rg in resolved_groups:
                try:
                    pending_user.groups.add(rg)
                except Exception:
                    pass

return True
'''

def is_valid_human_user(user: Dict[str, Any]) -> bool:
    """
    Checks if a user dictionary represents a legitimate human user and NOT a service account,
    internal system account, or anonymous user.
    """
    if not isinstance(user, dict):
        return False
    u_type = str(user.get("type") or "").strip().lower()
    if u_type in ("service_account", "internal"):
        return False
    username = str(user.get("username") or "").strip().lower()
    if not username:
        return False
    if username in ("anonymoususer", "anonymous", "akadmin"):
        return False
    if username.startswith(("service-", "service_", "ak-", "authentik-", "internal-", "bot-")):
        return False
    name = str(user.get("name") or "").strip().lower()
    if name.startswith(("service-", "service_", "ak-", "authentik-", "internal-", "bot-")):
        return False
    return True

class InviteService:
    async def create_invite(self, req: CreateInviteRequest, actor: str = "Admin") -> TrackedInviteSchema:
        expires_at: Optional[str] = None
        if req.expires_in_days > 0:
            exp_dt = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)
            expires_at = exp_dt.isoformat()

        # Resolve group names so fixed_data is compatible with external policies expecting names or UUIDs
        all_groups = await authentik_client.get_groups()
        group_pk_to_name = {str(g["pk"]): g["name"] for g in all_groups}
        target_group_names = [group_pk_to_name[pk] for pk in req.group_pks if pk in group_pk_to_name]

        # Authentik Invitation 'name' is a SlugField (^[a-zA-Z0-9_-]+$, max 50 chars)
        clean_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', req.name.strip().lower()).strip('-')
        clean_slug = clean_slug[:30].strip('-')
        invite_slug = f"invite-{clean_slug}-{secrets.token_hex(4)}" if clean_slug else f"invite-{secrets.token_hex(4)}"

        fixed_data = {
            "groups": req.group_pks,
            "groups_to_add": req.group_pks + target_group_names,
            "group_names": target_group_names,
            "assigned_apps": req.app_names,
            "invitation_slug": invite_slug,
            "attributes": {
                "invitation_slug": invite_slug,
                "invited_name": req.name.strip(),
            },
            "attributes.invitation_slug": invite_slug,
            "attributes.invited_name": req.name.strip(),
        }
        if req.email:
            fixed_data["email"] = req.email.strip()
        if req.phone:
            fixed_data["phone"] = req.phone.strip()
            fixed_data["attributes"]["phone"] = req.phone.strip()
            fixed_data["attributes.phone"] = req.phone.strip()

        # 1. Create invitation in Authentik
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

    async def _assign_groups_and_mark_redeemed(
        self,
        invite: Any,
        user: Dict[str, Any],
        actor: str = "AUTO_SYNC_WORKER"
    ) -> bool:
        """
        Helper that assigns pre-configured groups to the given user and updates invite status.
        """
        try:
            user_pk = user.get("pk")
            if isinstance(user_pk, str) and user_pk.isdigit():
                user_pk = int(user_pk)

            if not user_pk or not isinstance(user_pk, int) or user_pk <= 0:
                logger.warning(f"Cannot assign groups: invalid user_pk={user_pk}")
                return False

            if not is_valid_human_user(user):
                logger.warning(
                    f"Refusing to assign groups to non-human/service user: {user.get('username')} (pk={user_pk})"
                )
                return False

            username = str(user.get("username") or user.get("email") or f"User #{user_pk}")
            assigned_groups = json.loads(invite["assigned_groups"])
            db_path = get_db_path()

            logger.info(
                f"[ASSIGN_GROUPS] Beginning assignment of {len(assigned_groups)} groups to user '{username}' "
                f"(pk={user_pk}) for invite #{invite['id']} ('{invite['name']}')."
            )

            # Assign groups via Authentik API
            assigned_count = 0
            for g_pk in assigned_groups:
                try:
                    await authentik_client.add_user_to_group(g_pk, user_pk)
                    assigned_count += 1
                    logger.info(f"[ASSIGN_GROUPS] Successfully added user {username} (pk={user_pk}) to group {g_pk}")
                except Exception as e:
                    logger.warning(f"[ASSIGN_GROUPS] Failed adding user {username} (pk={user_pk}) to group {g_pk}: {e}")

            # Mark redeemed in DB (and populate email if it was previously empty)
            target_user_email = user.get("email")
            async with aiosqlite.connect(db_path) as db:
                if target_user_email and not invite["email"]:
                    await db.execute(
                        "UPDATE tracked_invites SET status = 'redeemed', redeemed_by = ?, email = ? WHERE id = ?",
                        (f"{username} (#{user_pk})", str(target_user_email).strip().lower(), invite["id"])
                    )
                else:
                    await db.execute(
                        "UPDATE tracked_invites SET status = 'redeemed', redeemed_by = ? WHERE id = ?",
                        (f"{username} (#{user_pk})", invite["id"])
                    )
                await db.commit()

            logger.info(f"[ASSIGN_GROUPS] Marked invite #{invite['id']} as 'redeemed' by {username} (#{user_pk}) in database.")

            audit_status = "SUCCESS" if assigned_count == len(assigned_groups) else ("WARNING" if assigned_count > 0 else "FAILED")
            await audit_service.log(
                actor=actor,
                action="AUTO_ASSIGN_INVITE_GROUPS",
                target_type="USER",
                target_name=username,
                target_id=str(user_pk),
                details=f"Assigned {assigned_count}/{len(assigned_groups)} groups from invite #{invite['id']} ({invite['name']})",
                status=audit_status
            )

            try:
                assigned_apps_list = json.loads(invite["assigned_apps"])
                from app.services.notification_service import notification_service
                await notification_service.notify_invite_redeemed(
                    user_name=user.get("name") or username,
                    user_email=user.get("email"),
                    assigned_apps=assigned_apps_list
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch redemption notification: {e}")

            return True
        except Exception as e:
            logger.error(f"Error in _assign_groups_and_mark_redeemed: {e}", exc_info=True)
            return False

    async def handle_webhook_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes an incoming webhook from Authentik (Notification Transport, Event Rule,
        or Expression Policy HTTP ping) and assigns pre-selected groups to the newly registered user.
        """
        try:
            # 1. Extract potential user identifiers from various payload formats
            email = (
                payload.get("email")
                or payload.get("event_user_email")
                or payload.get("user_email")
                or (payload.get("user", {}).get("email") if isinstance(payload.get("user"), dict) else None)
                or (payload.get("context", {}).get("email") if isinstance(payload.get("context"), dict) else None)
                or (payload.get("context", {}).get("prompt_data", {}).get("email") if isinstance(payload.get("context"), dict) and isinstance(payload.get("context", {}).get("prompt_data"), dict) else None)
            )
            username = (
                payload.get("username")
                or payload.get("event_user_username")
                or payload.get("user_username")
                or (payload.get("user", {}).get("username") if isinstance(payload.get("user"), dict) else None)
                or (payload.get("context", {}).get("username") if isinstance(payload.get("context"), dict) else None)
            )
            user_pk = (
                payload.get("user_pk")
                or payload.get("pk")
                or (payload.get("user", {}).get("pk") if isinstance(payload.get("user"), dict) else None)
                or (payload.get("context", {}).get("model", {}).get("pk") if isinstance(payload.get("context"), dict) and isinstance(payload.get("context", {}).get("model"), dict) else None)
            )
            invitation_pk = (
                payload.get("invitation_pk")
                or payload.get("itoken")
                or (payload.get("context", {}).get("invitation", {}).get("pk") if isinstance(payload.get("context"), dict) and isinstance(payload.get("context", {}).get("invitation"), dict) else None)
            )

            email_norm = str(email).strip().lower() if email else None
            username_norm = str(username).strip().lower() if username else None
            inv_pk_norm = str(invitation_pk).strip() if invitation_pk else None

            logger.info(
                f"[WEBHOOK_EVENT] Extracted target identifiers: email='{email_norm}', "
                f"username='{username_norm}', user_pk='{user_pk}', invitation_pk='{inv_pk_norm}'"
            )

            # 2. Lookup matching user in Authentik with retry to ensure Authentik DB write is finished
            matched_user = None
            for attempt in range(3):
                all_users = await authentik_client.get_users()
                human_users = [u for u in all_users if is_valid_human_user(u)]
                logger.info(
                    f"[WEBHOOK_EVENT] User lookup attempt {attempt+1}/3: fetched {len(all_users)} total Authentik users "
                    f"({len(human_users)} human users)."
                )
                if user_pk:
                    matched_user = next((u for u in human_users if str(u.get("pk")) == str(user_pk)), None)
                    if matched_user:
                        logger.info(f"[WEBHOOK_EVENT] Matched human user by user_pk={user_pk}: '{matched_user.get('username')}'")
                if not matched_user and email_norm:
                    matched_user = next((u for u in human_users if str(u.get("email") or "").strip().lower() == email_norm), None)
                    if matched_user:
                        logger.info(f"[WEBHOOK_EVENT] Matched human user by email='{email_norm}': '{matched_user.get('username')}'")
                if not matched_user and username_norm:
                    matched_user = next((u for u in human_users if str(u.get("username") or "").strip().lower() == username_norm), None)
                    if matched_user:
                        logger.info(f"[WEBHOOK_EVENT] Matched human user by username='{username_norm}': '{matched_user.get('username')}'")
                if matched_user:
                    break
                if attempt < 2:
                    logger.info(f"[WEBHOOK_EVENT] User not found yet on attempt {attempt+1}. Waiting 1.5s for Authentik commit...")
                    await asyncio.sleep(1.5)

            if not matched_user:
                logger.warning(
                    f"[WEBHOOK_EVENT] Human user could not be resolved in Authentik after 3 attempts "
                    f"(email='{email_norm}', username='{username_norm}', user_pk='{user_pk}'). Triggering sync_redemptions() fallback."
                )
                redeemed = await self.sync_redemptions()
                return {"status": "pending_sync", "redeemed_count": redeemed, "reason": "User not resolved in Authentik DB yet"}

            if not is_valid_human_user(matched_user):
                logger.warning(f"[WEBHOOK_EVENT] Matched non-human user '{matched_user.get('username')}'. Ignoring.")
                return {"status": "ignored", "reason": f"Matched user '{matched_user.get('username')}' is a service/system account"}

            target_pk = matched_user.get("pk")
            target_username = str(matched_user.get("username") or matched_user.get("email") or f"User #{target_pk}")
            target_email = str(matched_user.get("email") or "").strip().lower()

            logger.info(f"[WEBHOOK_EVENT] Resolved human user: username='{target_username}', pk={target_pk}, email='{target_email}'")

            # 3. Find pending invite in tracked_invites
            db_path = get_db_path()
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM tracked_invites WHERE status = 'pending' ORDER BY id DESC") as cursor:
                    pending_invites = await cursor.fetchall()

            if not pending_invites:
                logger.info(f"[WEBHOOK_EVENT] No pending invites in database to fulfill for user {target_username}.")
                return {"status": "ignored", "reason": "No pending invites in database"}

            logger.info(f"[WEBHOOK_EVENT] Evaluating {len(pending_invites)} pending invite(s) for user '{target_username}'...")

            matched_invite = None
            match_reason = ""

            # Check 1: Invitation PK
            if inv_pk_norm:
                matched_invite = next((i for i in pending_invites if str(i["invitation_pk"] or "") == inv_pk_norm), None)
                if matched_invite:
                    match_reason = f"Check 1: Exact invitation_pk match ({inv_pk_norm})"
                    logger.info(f"[WEBHOOK_EVENT] -> {match_reason} -> matched invite #{matched_invite['id']} ('{matched_invite['name']}')")

            # Check 2: Target Email
            if not matched_invite and target_email:
                matched_invite = next((i for i in pending_invites if str(i["email"] or "").strip().lower() == target_email), None)
                if matched_invite:
                    match_reason = f"Check 2: Target email match ({target_email})"
                    logger.info(f"[WEBHOOK_EVENT] -> {match_reason} -> matched invite #{matched_invite['id']} ('{matched_invite['name']}')")

            # Check 3: Check consumed single-use invites from Authentik
            if not matched_invite:
                try:
                    active_invs = await authentik_client.get_invitations()
                    active_pks = {str(a.get("pk")) for a in active_invs}
                    logger.info(f"[WEBHOOK_EVENT] Check 3: Active Authentik invitation PKs count: {len(active_pks)}")
                    for i in pending_invites:
                        if i["single_use"] and str(i["invitation_pk"]) not in active_pks:
                            i_email = str(i["email"] or "").strip().lower()
                            if not i_email or not target_email or i_email == target_email:
                                matched_invite = i
                                match_reason = f"Check 3: Consumed single-use invite #{i['id']} ({i['invitation_pk']})"
                                logger.info(f"[WEBHOOK_EVENT] -> {match_reason}")
                                break
                except Exception as e:
                    logger.warning(f"[WEBHOOK_EVENT] Check 3: Failed fetching active invitations: {e}")

            # Check 4: Name match
            if not matched_invite:
                for i in pending_invites:
                    inv_name = str(i["name"] or "").strip().lower()
                    i_email = str(i["email"] or "").strip().lower()
                    if target_email and i_email and target_email != i_email:
                        continue
                    if inv_name and len(inv_name) >= 3:
                        if (target_username and inv_name in target_username.lower()) or (target_email and inv_name in target_email):
                            matched_invite = i
                            match_reason = f"Check 4: Recipient name substring match ('{inv_name}')"
                            logger.info(f"[WEBHOOK_EVENT] -> {match_reason} -> matched invite #{i['id']}")
                            break

            # Check 5: If single pending invite exists without conflicting email
            if not matched_invite and len(pending_invites) == 1:
                single_inv = pending_invites[0]
                inv_em = str(single_inv["email"] or "").strip().lower()
                if not inv_em or not target_email or inv_em == target_email:
                    matched_invite = single_inv
                    match_reason = f"Check 5: Single pending invite fallback (#{single_inv['id']})"
                    logger.info(f"[WEBHOOK_EVENT] -> {match_reason}")

            if not matched_invite:
                pending_ids = [dict(i)["id"] for i in pending_invites]
                logger.warning(
                    f"[WEBHOOK_EVENT] Webhook received but no pending invite matched user '{target_username}' "
                    f"(email: '{target_email}', inv_pk: '{inv_pk_norm}'). Pending invite IDs: {pending_ids}"
                )
                return {
                    "status": "ignored",
                    "reason": f"No pending invite matched user '{target_username}' (email: '{target_email}', inv_pk: '{inv_pk_norm}')"
                }

            # 4. Assign groups and mark redeemed
            logger.info(f"[WEBHOOK_EVENT] Assigning groups for matched invite #{matched_invite['id']} ({match_reason})")
            success = await self._assign_groups_and_mark_redeemed(
                invite=matched_invite,
                user=matched_user,
                actor="AUTHENTIK_WEBHOOK"
            )

            assigned_groups = json.loads(matched_invite["assigned_groups"])
            return {
                "status": "success" if success else "failed",
                "user": target_username,
                "user_pk": target_pk,
                "invite_id": matched_invite["id"],
                "assigned_groups_count": len(assigned_groups),
                "match_reason": match_reason
            }
        except Exception as e:
            logger.error(f"Error handling Authentik webhook: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def _repair_misassigned_invites(
        self,
        human_users: List[Dict[str, Any]],
        all_users: List[Dict[str, Any]]
    ) -> int:
        """
        Auto-repairs any tracked invites that were mistakenly claimed by service accounts or bots:
        1. Revokes the misassigned groups from the service account in Authentik.
        2. If the intended human user is now registered in Authentik, assigns the groups to them.
        3. If the human user has not yet registered, resets the invite to 'pending' with redeemed_by=NULL.
        """
        db_path = get_db_path()
        repaired_count = 0
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT * FROM tracked_invites 
                    WHERE status = 'redeemed' 
                      AND (
                        redeemed_by LIKE '%service-%' 
                        OR redeemed_by LIKE '%whatsapp%' 
                        OR redeemed_by LIKE '%bot%' 
                        OR redeemed_by LIKE '%ak-%'
                      )
                    """
                ) as cursor:
                    corrupted_invites = await cursor.fetchall()

            if not corrupted_invites:
                return 0

            logger.info(f"Auto-repair: Found {len(corrupted_invites)} misassigned invite(s) claimed by service accounts.")

            human_by_email = {str(u.get("email") or "").strip().lower(): u for u in human_users if u.get("email")}
            human_by_username = {str(u.get("username") or "").strip().lower(): u for u in human_users if u.get("username")}

            for inv in corrupted_invites:
                inv_id = inv["id"]
                redeemed_by = inv["redeemed_by"] or ""
                assigned_groups = json.loads(inv["assigned_groups"] or "[]")
                inv_email = str(inv["email"] or "").strip().lower()
                inv_name = str(inv["name"] or "").strip()

                # Extract bot PK from redeemed_by string (e.g. "service-whatsapp-bot (#12)")
                match = re.search(r'#(\d+)', redeemed_by)
                bot_pk = int(match.group(1)) if match else None
                if not bot_pk:
                    bot_name = redeemed_by.split(" (")[0].strip().lower()
                    for u in all_users:
                        if str(u.get("username") or "").strip().lower() == bot_name:
                            bot_pk = u.get("pk")
                            break

                # Remove misassigned groups from the service account in Authentik
                if bot_pk and assigned_groups:
                    for g_pk in assigned_groups:
                        try:
                            await authentik_client.remove_user_from_group(g_pk, bot_pk)
                            logger.info(f"Auto-repair: Removed group {g_pk} from bot {redeemed_by}")
                        except Exception as e:
                            logger.warning(f"Auto-repair: Could not remove group {g_pk} from bot {bot_pk}: {e}")

                # Locate the intended human user in Authentik
                real_user = None
                if inv_email and inv_email in human_by_email:
                    real_user = human_by_email[inv_email]
                elif inv_email and inv_email in human_by_username:
                    real_user = human_by_username[inv_email]
                elif inv_name and len(inv_name) >= 3:
                    inv_lower = inv_name.lower()
                    for u in human_users:
                        u_email = str(u.get("email") or "").strip().lower()
                        u_user = str(u.get("username") or "").strip().lower()
                        u_name = str(u.get("name") or "").strip().lower()
                        if (u_name and inv_lower in u_name) or (u_user and inv_lower in u_user) or (u_email and inv_lower in u_email):
                            real_user = u
                            break

                if real_user:
                    # Intended user is already enrolled! Assign groups to them
                    real_pk = int(real_user["pk"])
                    real_username = str(real_user.get("username") or real_user.get("email") or f"User #{real_pk}")
                    assigned_count = 0
                    for g_pk in assigned_groups:
                        try:
                            await authentik_client.add_user_to_group(g_pk, real_pk)
                            assigned_count += 1
                        except Exception as e:
                            logger.warning(f"Auto-repair: Error assigning group {g_pk} to {real_username}: {e}")

                    async with aiosqlite.connect(db_path) as db:
                        await db.execute(
                            "UPDATE tracked_invites SET status = 'redeemed', redeemed_by = ? WHERE id = ?",
                            (f"{real_username} (#{real_pk})", inv_id)
                        )
                        await db.commit()

                    await audit_service.log(
                        actor="AUTO_REPAIR_WORKER",
                        action="AUTO_ASSIGN_INVITE_GROUPS",
                        target_type="USER",
                        target_name=real_username,
                        target_id=str(real_pk),
                        details=f"Auto-repaired invite #{inv_id} ({inv_name}): stripped misassigned groups from {redeemed_by} and assigned {assigned_count}/{len(assigned_groups)} groups to {real_username}",
                        status="SUCCESS"
                    )
                    repaired_count += 1
                else:
                    # Intended user has not enrolled yet. Reset invite to 'pending' so they get groups upon signup!
                    async with aiosqlite.connect(db_path) as db:
                        await db.execute(
                            "UPDATE tracked_invites SET status = 'pending', redeemed_by = NULL WHERE id = ?",
                            (inv_id,)
                        )
                        await db.commit()

                    await audit_service.log(
                        actor="AUTO_REPAIR_WORKER",
                        action="REPAIR_INVITE",
                        target_type="INVITATION",
                        target_name=inv_name,
                        target_id=str(inv_id),
                        details=f"Stripped misassigned groups from {redeemed_by} and restored invite #{inv_id} to 'pending' for {inv_email or inv_name}",
                        status="SUCCESS"
                    )
                    repaired_count += 1

        except Exception as e:
            logger.error(f"Error during _repair_misassigned_invites: {e}", exc_info=True)

        return repaired_count

    async def sync_redemptions(self) -> int:
        """
        Background & real-time sync: Matches newly created human users in Authentik against pending invites.
        Checks Authentik events ('invitation_used', 'login'), target email, active invitation lifecycle,
        and user signups to assign pre-selected groups via Authentik API. Also automatically repairs
        any past invites mistakenly claimed by service accounts.
        """
        try:
            # 1. Fetch current users from Authentik and partition human vs system accounts
            all_users = await authentik_client.get_users()
            human_users = [u for u in all_users if is_valid_human_user(u)]

            # 2. Run auto-repair on any invites previously hijacked by service accounts
            await self._repair_misassigned_invites(human_users, all_users)

            # 3. Fetch pending invites from local SQLite
            db_path = get_db_path()
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM tracked_invites WHERE status = 'pending' ORDER BY id DESC") as cursor:
                    pending = await cursor.fetchall()

            if not pending:
                return 0

            users_by_email = {
                str(u.get("email") or "").strip().lower(): u 
                for u in human_users if u.get("email")
            }
            users_by_username = {
                str(u.get("username") or "").strip().lower(): u 
                for u in human_users if u.get("username")
            }

            # 4. Fetch active invitations to detect consumed single-use invites
            active_inv_pks = set()
            try:
                active_invs = await authentik_client.get_invitations()
                active_inv_pks = {str(i.get("pk")) for i in active_invs}
            except Exception as e:
                logger.warning(f"Could not fetch active invitations: {e}")

            # 5. Fetch Authentik events (invitation_used, login)
            events_inv = await authentik_client.get_events(action="invitation_used", page_size=100)
            events_login = await authentik_client.get_events(action="login", page_size=100)

            # Correlate invitation_used with login events by client_ip (strictly human users only)
            inv_to_user: Dict[str, Dict[str, Any]] = {}
            for ev in events_inv:
                ev_context = ev.get("context", {})
                if isinstance(ev_context, dict):
                    ev_inv = ev_context.get("invitation")
                    ev_inv_pk = ""
                    ev_inv_name = ""
                    if isinstance(ev_inv, str):
                        ev_inv_pk = ev_inv.strip()
                    elif isinstance(ev_inv, dict):
                        ev_inv_pk = str(ev_inv.get("pk") or ev_inv.get("id") or "").strip()
                        ev_inv_name = str(ev_inv.get("name") or "").strip()
                    if not ev_inv_pk:
                        ev_inv_pk = str(ev_context.get("invitation_pk") or "").strip()

                    ev_ip = ev.get("client_ip")
                    ev_user = ev.get("user")
                    if ev_user and isinstance(ev_user, dict) and is_valid_human_user(ev_user):
                        if ev_inv_pk:
                            inv_to_user[ev_inv_pk] = ev_user
                        if ev_inv_name:
                            inv_to_user[ev_inv_name] = ev_user
                        continue

                    if ev_ip:
                        for log_ev in events_login:
                            log_user = log_ev.get("user")
                            if log_user and isinstance(log_user, dict) and log_ev.get("client_ip") == ev_ip:
                                if is_valid_human_user(log_user):
                                    if ev_inv_pk:
                                        inv_to_user[ev_inv_pk] = log_user
                                    if ev_inv_name:
                                        inv_to_user[ev_inv_name] = log_user
                                    break

            redeemed_count = 0
            logger.info(
                f"[SYNC_REDEMPTIONS] Evaluating {len(pending)} pending invite(s). "
                f"Authentik human users available: {len(human_users)}"
            )

            for invite in pending:
                matched_user = None
                matched_strategy = ""
                inv_pk = str(invite["invitation_pk"] or "")
                inv_name = str(invite["name"] or "")
                target_email = str(invite["email"] or "").strip().lower()
                target_phone = str(invite["phone"] or "").strip()

                logger.debug(
                    f"[SYNC_REDEMPTIONS] Evaluating invite #{invite['id']} ('{inv_name}', email='{target_email}', "
                    f"phone='{target_phone}', single_use={bool(invite['single_use'])})"
                )

                # Strategy 0: Direct Match via User Attributes (invitation_pk, invitation_slug, or phone)
                for u in human_users:
                    u_attrs = u.get("attributes") or {}
                    if not isinstance(u_attrs, dict):
                        continue
                    u_inv_pk = str(u_attrs.get("invitation_pk") or u_attrs.get("invitation") or "").strip()
                    u_inv_slug = str(u_attrs.get("invitation_slug") or "").strip().lower()
                    u_phone = str(u_attrs.get("phone") or u_attrs.get("phoneNumber") or "").strip()

                    if u_inv_pk and u_inv_pk == inv_pk:
                        matched_user = u
                        matched_strategy = f"Strategy 0 (user attribute invitation_pk={u_inv_pk})"
                        break
                    if u_inv_slug and inv_name and u_inv_slug == inv_name.lower():
                        matched_user = u
                        matched_strategy = f"Strategy 0 (user attribute invitation_slug={u_inv_slug})"
                        break
                    if target_phone and u_phone and (target_phone == u_phone or target_phone in u_phone or u_phone in target_phone):
                        matched_user = u
                        matched_strategy = f"Strategy 0 (user attribute phone={u_phone})"
                        break

                # Strategy 1: Check Authentik invitation_used event correlation
                if not matched_user:
                    if inv_pk and inv_pk in inv_to_user:
                        matched_user = inv_to_user[inv_pk]
                        matched_strategy = f"Strategy 1 (event correlation inv_pk={inv_pk})"
                    elif inv_name and inv_name in inv_to_user:
                        matched_user = inv_to_user[inv_name]
                        matched_strategy = f"Strategy 1 (event correlation inv_name={inv_name})"

                # Strategy 2: Match by target email if provided (check both email and username)
                if not matched_user and target_email:
                    if target_email in users_by_email:
                        matched_user = users_by_email[target_email]
                        matched_strategy = f"Strategy 2 (email match={target_email})"
                    elif target_email in users_by_username:
                        matched_user = users_by_username[target_email]
                        matched_strategy = f"Strategy 2 (username match={target_email})"

                # Strategy 3: Check single-use invitation consumption
                if not matched_user and invite["single_use"] and inv_pk and inv_pk not in active_inv_pks:
                    for u in human_users:
                        u_email = str(u.get("email") or "").strip().lower()
                        u_name = str(u.get("name") or "").strip().lower()
                        u_user = str(u.get("username") or "").strip().lower()
                        u_attrs = u.get("attributes") or {}
                        u_phone = str(u_attrs.get("phone") or u_attrs.get("phoneNumber") or "").strip() if isinstance(u_attrs, dict) else ""

                        if target_email and (target_email == u_email or target_email in u_user):
                            matched_user = u
                            matched_strategy = "Strategy 3 (consumed single-use + email/user match)"
                            break
                        if target_phone and u_phone and (target_phone == u_phone or target_phone in u_phone or u_phone in target_phone):
                            matched_user = u
                            matched_strategy = "Strategy 3 (consumed single-use + phone match)"
                            break
                        if inv_name and len(inv_name) >= 3:
                            inv_lower = inv_name.lower()
                            if (u_name and inv_lower in u_name) or (u_user and inv_lower in u_user):
                                matched_user = u
                                matched_strategy = "Strategy 3 (consumed single-use + name match)"
                                break

                # Strategy 4: Check users matching invite target email or invite recipient name
                if not matched_user:
                    for u in human_users:
                        u_email = str(u.get("email") or "").strip().lower()
                        u_name = str(u.get("name") or "").strip().lower()
                        u_user = str(u.get("username") or "").strip().lower()
                        
                        email_match = bool(target_email and (target_email == u_email or target_email in u_user))
                        
                        name_match = False
                        if inv_name and len(inv_name) >= 3:
                            inv_lower = inv_name.lower()
                            if (u_name and (inv_lower in u_name or u_name in inv_lower)) or \
                               (u_user and (inv_lower in u_user or u_user in inv_lower)):
                                name_match = True
                        
                        # Guard: If invite specifies an email and this user has a different email, do NOT match
                        if target_email and u_email and target_email != u_email:
                            continue

                        if email_match or name_match:
                            matched_user = u
                            matched_strategy = f"Strategy 4 (name/email match: email={email_match}, name={name_match})"
                            break

                if matched_user and is_valid_human_user(matched_user):
                    logger.info(
                        f"[SYNC_REDEMPTIONS] Matched pending invite #{invite['id']} ('{inv_name}') "
                        f"to user '{matched_user.get('username')}' (pk={matched_user.get('pk')}) via {matched_strategy}"
                    )
                    ok = await self._assign_groups_and_mark_redeemed(
                        invite=invite,
                        user=matched_user,
                        actor="AUTO_SYNC_WORKER"
                    )
                    if ok:
                        redeemed_count += 1
                else:
                    logger.debug(
                        f"[SYNC_REDEMPTIONS] Pending invite #{invite['id']} ('{inv_name}', email='{target_email}', "
                        f"pk='{inv_pk}') could not be matched to any user yet."
                    )

            return redeemed_count
        except Exception as e:
            logger.warning(f"Error during invite sync_redemptions: {e}", exc_info=True)
            return 0

    async def install_flow_policy(self) -> Dict[str, Any]:
        """
        Automatically provisions the Expression Policy into Authentik and binds it
        to the enrollment flow so that invited users are assigned to their checked apps
        instantly during registration.
        """
        policy_name = "authentik-manager-assign-invite-groups"

        # 1. Fetch or create Expression Policy in Authentik
        policies = await authentik_client.get_expression_policies()
        existing_policy = next((p for p in policies if p.get("name") == policy_name), None)

        if existing_policy:
            policy_pk = str(existing_policy["pk"])
            await authentik_client.update_expression_policy(
                policy_pk=policy_pk,
                name=policy_name,
                expression=EXPRESSION_POLICY_TEMPLATE
            )
        else:
            created = await authentik_client.create_expression_policy(
                name=policy_name,
                expression=EXPRESSION_POLICY_TEMPLATE
            )
            policy_pk = str(created["pk"])

        # 2. Find the Enrollment Flow
        flows = await authentik_client.get_flows()
        enrollment_flow = next(
            (f for f in flows if str(f.get("slug") or "") == settings.DEFAULT_ENROLLMENT_FLOW),
            None
        )
        if not enrollment_flow:
            enrollment_flow = next(
                (f for f in flows if str(f.get("designation") or "") == "enrollment"),
                None
            )
        if not enrollment_flow:
            enrollment_flow = next(
                (f for f in flows if "enrollment" in str(f.get("slug") or "").lower() or "invitation" in str(f.get("slug") or "").lower()),
                None
            )

        if not enrollment_flow:
            return {
                "status": "warning",
                "policy_pk": policy_pk,
                "message": f"Created policy '{policy_name}', but could not find enrollment flow '{settings.DEFAULT_ENROLLMENT_FLOW}'. Please bind it manually in Authentik."
            }

        flow_pk = str(enrollment_flow["pk"])

        # 3. Check if binding already exists
        bindings = await authentik_client.get_policy_bindings()
        already_bound = any(
            str(b.get("target")) == flow_pk and str(b.get("policy")) == policy_pk
            for b in bindings
        )

        if not already_bound:
            await authentik_client.bind_policy_to_flow(
                flow_pk=flow_pk,
                policy_pk=policy_pk,
                order=0
            )

        flow_display = enrollment_flow.get("name") or enrollment_flow.get("slug")
        return {
            "status": "success",
            "policy_pk": policy_pk,
            "flow_pk": flow_pk,
            "flow_slug": enrollment_flow.get("slug"),
            "message": f"Successfully installed policy '{policy_name}' and bound to enrollment flow '{flow_display}'."
        }

    @staticmethod
    def get_flow_guide() -> Dict[str, Any]:
        base_host = settings.APP_HOST if settings.APP_HOST not in ("0.0.0.0", "") else "authentik-manager"
        from app.services.settings_service import settings_service
        secret = settings_service.get_webhook_secret()

        webhook_url = f"http://{base_host}:{settings.APP_PORT}/api/webhooks/authentik"
        if secret:
            webhook_url += f"?token={secret}"

        webhook_snippet = f'''# Append this notification snippet to your Guest Write Expression Policy in Authentik:
# (Notifies Authentik Access Manager upon registration to assign pre-selected application groups)
inv = request.context.get("invitation")
inv_pk = str(getattr(inv, "pk", "") if inv else (request.context.get("prompt_data", {{}}).get("invitation_pk", "") or ""))

if "attributes" not in request.context["prompt_data"]:
    request.context["prompt_data"]["attributes"] = {{}}
if inv_pk:
    request.context["prompt_data"]["attributes"]["invitation_pk"] = inv_pk
prompt_phone = request.context.get("prompt_data", {{}}).get("phone")
if prompt_phone:
    request.context["prompt_data"]["attributes"]["phone"] = str(prompt_phone)

try:
    import urllib.request, json
    mgr_url = "{webhook_url}"
    payload = json.dumps({{
        "email": email,
        "username": email,
        "invitation_pk": inv_pk
    }}).encode("utf-8")
    ak_logger.info(f"Notifying Authentik Manager for user '{{email}}' (invite '{{inv_pk}}') at {{mgr_url}}")
    req = urllib.request.Request(mgr_url, data=payload, headers={{"Content-Type": "application/json"}})
    with urllib.request.urlopen(req, timeout=10) as resp:
        ak_logger.info(f"Authentik Manager webhook response status: {{resp.status}}")
except Exception as err:
    ak_logger.error(f"Failed to notify Authentik Manager webhook: {{err}}")
'''

        return {
            "title": "Authentik Group Assignment & Webhook Integration",
            "description": (
                "When users register via an invitation, Authentik can notify Authentik Access Manager via Webhook "
                "or Expression Policy ping to immediately assign application groups outside the flow."
            ),
            "webhook_url": webhook_url,
            "webhook_snippet": webhook_snippet,
            "snippet": EXPRESSION_POLICY_TEMPLATE
        }

invite_service = InviteService()
