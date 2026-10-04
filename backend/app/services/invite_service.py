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

        fixed_data = {
            "groups": req.group_pks,
            "groups_to_add": req.group_pks + target_group_names,
            "group_names": target_group_names,
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

            username = str(user.get("username") or user.get("email") or f"User #{user_pk}")
            assigned_groups = json.loads(invite["assigned_groups"])
            db_path = get_db_path()

            # Assign groups via Authentik API
            assigned_count = 0
            for g_pk in assigned_groups:
                try:
                    await authentik_client.add_user_to_group(g_pk, user_pk)
                    assigned_count += 1
                except Exception as e:
                    logger.warning(f"Error adding user {user_pk} to group {g_pk}: {e}")

            # Mark redeemed in DB
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "UPDATE tracked_invites SET status = 'redeemed', redeemed_by = ? WHERE id = ?",
                    (f"{username} (#{user_pk})", invite["id"])
                )
                await db.commit()

            await audit_service.log(
                actor=actor,
                action="AUTO_ASSIGN_INVITE_GROUPS",
                target_type="USER",
                target_name=username,
                target_id=str(user_pk),
                details=f"Assigned {assigned_count}/{len(assigned_groups)} groups from invite #{invite['id']} ({invite['name']})",
                status="SUCCESS"
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

            # 2. Lookup matching user in Authentik with retry to ensure Authentik DB write is finished
            matched_user = None
            for attempt in range(3):
                users = await authentik_client.get_users()
                if user_pk:
                    matched_user = next((u for u in users if str(u.get("pk")) == str(user_pk)), None)
                if not matched_user and email_norm:
                    matched_user = next((u for u in users if str(u.get("email") or "").strip().lower() == email_norm), None)
                if not matched_user and username_norm:
                    matched_user = next((u for u in users if str(u.get("username") or "").strip().lower() == username_norm), None)
                if matched_user:
                    break
                if attempt < 2:
                    await asyncio.sleep(1.5)

            if not matched_user:
                logger.info(f"Webhook received but user not resolved in Authentik yet (email={email}, user={username}). Triggering sync.")
                redeemed = await self.sync_redemptions()
                return {"status": "pending_sync", "redeemed_count": redeemed}

            target_pk = matched_user.get("pk")
            target_username = str(matched_user.get("username") or matched_user.get("email") or f"User #{target_pk}")
            target_email = str(matched_user.get("email") or "").strip().lower()

            # 3. Find pending invite in tracked_invites
            db_path = get_db_path()
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM tracked_invites WHERE status = 'pending' ORDER BY id DESC") as cursor:
                    pending_invites = await cursor.fetchall()

            if not pending_invites:
                logger.info("No pending invites to fulfill for webhook.")
                return {"status": "ignored", "reason": "No pending invites in database"}

            matched_invite = None
            # Check 1: Invitation PK
            if inv_pk_norm:
                matched_invite = next((i for i in pending_invites if str(i["invitation_pk"] or "") == inv_pk_norm), None)

            # Check 2: Target Email
            if not matched_invite and target_email:
                matched_invite = next((i for i in pending_invites if str(i["email"] or "").strip().lower() == target_email), None)

            # Check 3: Check consumed single-use invites from Authentik
            if not matched_invite:
                try:
                    active_invs = await authentik_client.get_invitations()
                    active_pks = {str(a.get("pk")) for a in active_invs}
                    for i in pending_invites:
                        if i["single_use"] and str(i["invitation_pk"]) not in active_pks:
                            matched_invite = i
                            break
                except Exception:
                    pass

            # Check 4: Name match
            if not matched_invite:
                for i in pending_invites:
                    inv_name = str(i["name"] or "").strip().lower()
                    if inv_name and len(inv_name) >= 3:
                        if inv_name in target_username.lower() or inv_name in target_email or target_username.lower() in inv_name:
                            matched_invite = i
                            break

            # Check 5: If single pending invite exists or latest created
            if not matched_invite:
                matched_invite = pending_invites[0]

            # 4. Assign groups and mark redeemed
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
                "assigned_groups_count": len(assigned_groups)
            }
        except Exception as e:
            logger.error(f"Error handling Authentik webhook: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def sync_redemptions(self) -> int:
        """
        Background & real-time sync: Matches newly created users in Authentik against pending invites.
        Checks Authentik events ('invitation_used', 'login'), target email, active invitation lifecycle,
        and recent user signups to assign pre-selected groups via Authentik API.
        """
        try:
            db_path = get_db_path()
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM tracked_invites WHERE status = 'pending' ORDER BY id DESC") as cursor:
                    pending = await cursor.fetchall()

            if not pending:
                return 0

            # 1. Fetch current users from Authentik
            users = await authentik_client.get_users()
            users_by_email = {
                str(u.get("email") or "").strip().lower(): u 
                for u in users if u.get("email")
            }
            users_by_username = {
                str(u.get("username") or "").strip().lower(): u 
                for u in users if u.get("username")
            }

            # 2. Fetch active invitations to detect consumed single-use invites
            active_inv_pks = set()
            try:
                active_invs = await authentik_client.get_invitations()
                active_inv_pks = {str(i.get("pk")) for i in active_invs}
            except Exception as e:
                logger.warning(f"Could not fetch active invitations: {e}")

            # 3. Fetch Authentik events (invitation_used, login)
            events_inv = await authentik_client.get_events(action="invitation_used", page_size=100)
            events_login = await authentik_client.get_events(action="login", page_size=50)

            # Correlate invitation_used with login events by client_ip
            inv_to_user: Dict[str, Dict[str, Any]] = {}
            for ev in events_inv:
                ev_context = ev.get("context", {})
                if isinstance(ev_context, dict):
                    ev_inv = ev_context.get("invitation", {})
                    if isinstance(ev_inv, dict):
                        ev_inv_pk = str(ev_inv.get("pk") or "")
                        ev_inv_name = str(ev_inv.get("name") or "")
                        ev_ip = ev.get("client_ip")

                        ev_user = ev.get("user")
                        if ev_user and isinstance(ev_user, dict):
                            u_name = str(ev_user.get("username") or "").lower()
                            u_pk = ev_user.get("pk")
                            if u_pk and u_name not in ("anonymoususer", "anonymous", ""):
                                if ev_inv_pk:
                                    inv_to_user[ev_inv_pk] = ev_user
                                if ev_inv_name:
                                    inv_to_user[ev_inv_name] = ev_user
                                continue

                        if ev_ip:
                            for log_ev in events_login:
                                log_user = log_ev.get("user")
                                if log_user and isinstance(log_user, dict) and log_ev.get("client_ip") == ev_ip:
                                    lu_name = str(log_user.get("username") or "").lower()
                                    if lu_name not in ("anonymoususer", "anonymous", ""):
                                        if ev_inv_pk:
                                            inv_to_user[ev_inv_pk] = log_user
                                        if ev_inv_name:
                                            inv_to_user[ev_inv_name] = log_user
                                        break

            redeemed_count = 0

            for invite in pending:
                matched_user = None
                inv_pk = str(invite["invitation_pk"] or "")
                inv_name = str(invite["name"] or "")
                target_email = str(invite["email"] or "").strip().lower()

                # Strategy 1: Check Authentik invitation_used event correlation
                if inv_pk and inv_pk in inv_to_user:
                    matched_user = inv_to_user[inv_pk]
                elif inv_name and inv_name in inv_to_user:
                    matched_user = inv_to_user[inv_name]

                # Strategy 2: Match by target email if provided
                if not matched_user and target_email and target_email in users_by_email:
                    matched_user = users_by_email[target_email]

                # Strategy 3: Check single-use invitation consumption
                if not matched_user and invite["single_use"] and inv_pk and inv_pk not in active_inv_pks:
                    for u in users:
                        u_email = str(u.get("email") or "").strip().lower()
                        u_name = str(u.get("name") or "").strip().lower()
                        u_user = str(u.get("username") or "").strip().lower()
                        if target_email and (target_email == u_email or target_email in u_user):
                            matched_user = u
                            break
                        if inv_name and len(inv_name) >= 3 and (inv_name.lower() in u_name or inv_name.lower() in u_user):
                            matched_user = u
                            break
                    if not matched_user and len(pending) == 1 and users:
                        matched_user = max(users, key=lambda x: x.get("pk", 0))

                # Strategy 4: Check users matching invite name
                if not matched_user:
                    for u in users:
                        u_email = str(u.get("email") or "").strip().lower()
                        u_name = str(u.get("name") or "").strip().lower()
                        u_user = str(u.get("username") or "").strip().lower()
                        email_match = bool(target_email and target_email == u_email)
                        name_match = bool(
                            inv_name and len(inv_name) >= 3 and
                            (inv_name.lower() in u_name or inv_name.lower() in u_user or u_name in inv_name.lower())
                        )
                        if email_match or name_match:
                            matched_user = u
                            break

                if matched_user:
                    ok = await self._assign_groups_and_mark_redeemed(
                        invite=invite,
                        user=matched_user,
                        actor="AUTO_SYNC_WORKER"
                    )
                    if ok:
                        redeemed_count += 1

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
try:
    import urllib.request, json
    mgr_url = "{webhook_url}"
    payload = json.dumps({{
        "email": email,
        "username": email,
        "invitation_pk": str(request.context.get("invitation", {{}}).get("pk", "") if isinstance(request.context.get("invitation"), dict) else getattr(request.context.get("invitation"), "pk", ""))
    }}).encode("utf-8")
    req = urllib.request.Request(mgr_url, data=payload, headers={{"Content-Type": "application/json"}})
    urllib.request.urlopen(req, timeout=2)
except Exception:
    pass
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
