import re
import shlex
import logging
from typing import Optional, List, Dict, Any
from app.config import settings
from app.services.settings_service import settings_service
from app.services.matrix_service import matrix_service
from app.services.template_service import template_service
from app.services.invite_service import invite_service
from app.services.audit_service import audit_service
from app.models import CreateInviteRequest

logger = logging.getLogger("authentik_manager.bot_service")

class BotService:
    def is_admin_phone(self, sender: str) -> bool:
        """
        Validates if the sender phone number matches configured admin numbers.
        sender is typically digits from WhatsApp JID, e.g. '447123456789'.
        """
        allowed_raw = settings_service._admin_phone_numbers
        if not allowed_raw or not allowed_raw.strip():
            return False

        if allowed_raw.strip() == "*":
            return True

        sender_digits = re.sub(r"\D", "", sender)
        if not sender_digits:
            return False

        allowed_list = [p.strip() for p in allowed_raw.split(",") if p.strip()]
        for admin_entry in allowed_list:
            admin_digits = re.sub(r"\D", "", admin_entry)
            if not admin_digits:
                continue

            # Check direct match
            if sender_digits == admin_digits:
                return True

            # If admin number starts with 0 (e.g. 07123456789) and sender has country code (e.g. 447123456789)
            if admin_entry.startswith("0") and settings.DEFAULT_COUNTRY_CODE:
                with_cc = settings.DEFAULT_COUNTRY_CODE + admin_digits[1:]
                if sender_digits == with_cc:
                    return True

            # Suffix match (e.g. sender has full country code, admin entered national format)
            if sender_digits.endswith(admin_digits) or admin_digits.endswith(sender_digits):
                return True

        return False

    def is_admin_telegram_chat(self, chat_id: str) -> bool:
        allowed_raw = settings_service._telegram_admin_chat_ids
        if not allowed_raw or not allowed_raw.strip():
            return False
        if allowed_raw.strip() == "*":
            return True
        allowed_list = [c.strip() for c in allowed_raw.split(",") if c.strip()]
        return str(chat_id).strip() in allowed_list

    def handle_help(self, channel: str = "whatsapp") -> str:
        prefix = "/" if channel == "telegram" else "!"
        return (
            "🤖 *Authentik Manager Bot*\n\n"
            "Available Commands:\n"
            f"• `{prefix}status` - System health, users, apps & active passes\n"
            f"• `{prefix}presets` - View access templates & application bundles\n"
            f"• `{prefix}invite <Name> <Preset or Apps> [days]` - Generate an invitation link\n"
            f"• `{prefix}help` - Display this command menu\n\n"
            "_Examples:_\n"
            f"• `{prefix}invite Alice \"Guest Access\"`\n"
            f"• `{prefix}invite Bob Plex,Jellyfin 3`\n"
            f"• `{prefix}invite Charlie 1 7` (by preset #ID)"
        )

    async def handle_status(self) -> str:
        try:
            conn = await settings_service.test_authentik_connection()
            matrix = await matrix_service.get_matrix()
            total_users = len(matrix.users)
            total_apps = len(matrix.apps)
            unprotected = sum(1 for a in matrix.apps if not a.is_protected)
            total_leases = sum(len(grants) for grants in matrix.expiring_grants.values())

            status_text = "🟢 Connected" if conn.success else "🔴 Connection Error"
            version_text = f" (v{conn.version})" if conn.version else ""

            return (
                "📊 *Authentik Manager Status*\n\n"
                f"• *Status:* {status_text}{version_text}\n"
                f"• *Authentik Host:* `{settings.AUTHENTIK_URL}`\n"
                f"• *Users:* *{total_users}*\n"
                f"• *Applications:* *{total_apps}* ({unprotected} unprotected)\n"
                f"• *Active Guest Passes:* *{total_leases}*\n"
                f"• *Enforcement:* Default-Deny active"
            )
        except Exception as e:
            logger.error(f"Error executing bot !status: {e}")
            return f"⚠️ Error fetching system status: {str(e)}"

    async def handle_presets(self) -> str:
        try:
            templates = await template_service.list_templates()
            if not templates:
                return (
                    "ℹ️ No access presets configured yet.\n\n"
                    "You can create presets (e.g. 'Streaming Guest', 'Family') in the web dashboard under Presets."
                )

            lines = ["📋 *Available Access Presets:*\n"]
            for t in templates:
                app_count = len(t.assignments)
                desc = f" - _{t.description}_" if t.description else ""
                lines.append(f"• [#{t.id}] *{t.name}* ({app_count} apps){desc}")

            lines.append("\n_Usage:_ `!invite <Name> <PresetName or #ID> [days]`")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error executing bot !presets: {e}")
            return f"⚠️ Error listing presets: {str(e)}"

    async def handle_invite(self, sender: str, tokens: List[str], channel: str = "whatsapp") -> str:
        if len(tokens) < 3:
            return (
                "⚠️ *Invalid syntax*\n\n"
                "Usage: `!invite <Name> <Preset or Apps> [days]`\n"
                "_Example:_ `!invite Alice \"Guest Access\" 7`\n"
                "_Example:_ `!invite Bob Plex,Jellyfin 3`"
            )

        name = tokens[1].strip()
        target = tokens[2].strip()

        # Parse days
        days = settings_service._default_invite_expiry_days or 7
        if len(tokens) >= 4:
            clean_days = re.sub(r"\D", "", tokens[3])
            if clean_days.isdigit() and int(clean_days) > 0:
                days = int(clean_days)

        try:
            templates = await template_service.list_templates()
            matrix = await matrix_service.get_matrix()

            matched_template = None
            target_clean = target.lstrip("#")
            if target_clean.isdigit():
                tid = int(target_clean)
                matched_template = next((t for t in templates if t.id == tid), None)

            if not matched_template:
                # Name match
                matched_template = next((t for t in templates if t.name.lower() == target.lower()), None)
                if not matched_template:
                    matched_template = next((t for t in templates if target.lower() in t.name.lower()), None)

            group_pks: List[str] = []
            app_names: List[str] = []

            if matched_template:
                assignments = matched_template.assignments
                is_wildcard = "*" in assignments
                wildcard_role = assignments.get("*", "member")

                for app in matrix.apps:
                    role = None
                    if app.pk in assignments:
                        role = assignments[app.pk]
                    elif app.slug in assignments:
                        role = assignments[app.slug]
                    elif is_wildcard:
                        role = wildcard_role

                    if role:
                        gp = app.granular_admin_group_pk if (role == "admin" and app.granular_admin_group_pk) else (app.granular_user_group_pk or app.bound_group_pk)
                        if gp and gp not in group_pks:
                            group_pks.append(gp)
                        app_names.append(app.name)
            else:
                # Comma separated apps
                requested_apps = [a.strip() for a in target.split(",") if a.strip()]
                for req_app in requested_apps:
                    req_lower = req_app.lower()
                    matched_app = next(
                        (a for a in matrix.apps if a.name.lower() == req_lower or a.slug.lower() == req_lower),
                        None
                    )
                    if not matched_app:
                        matched_app = next(
                            (a for a in matrix.apps if req_lower in a.name.lower() or req_lower in a.slug.lower()),
                            None
                        )
                    if matched_app:
                        gp = matched_app.granular_user_group_pk or matched_app.bound_group_pk
                        if gp and gp not in group_pks:
                            group_pks.append(gp)
                        app_names.append(matched_app.name)

            if not app_names:
                return (
                    f"❌ Could not find preset or application matching '{target}'.\n"
                    "Type `!presets` to see available presets or use comma-separated app names."
                )

            # Create invite
            invite_req = CreateInviteRequest(
                name=name,
                expires_in_days=days,
                single_use=True,
                group_pks=group_pks,
                app_names=app_names,
                send_via_whatsapp=False,
                template_id=matched_template.id if matched_template else None
            )

            actor_label = f"Telegram Bot ({sender})" if channel == "telegram" else f"WhatsApp Bot (+{sender})"
            invite_res = await invite_service.create_invite(invite_req, actor=actor_label)

            await audit_service.log(
                actor=actor_label,
                action="BOT_CREATE_INVITE",
                target_type="INVITATION",
                target_name=name,
                target_id=invite_res.invitation_pk,
                details=f"Generated invite via {channel.capitalize()} for {len(app_names)} services",
                status="SUCCESS"
            )

            apps_display = ", ".join(app_names[:6])
            if len(app_names) > 6:
                apps_display += f" and {len(app_names) - 6} more"

            return (
                f"🎉 *Invitation Generated!*\n\n"
                f"👤 *Recipient:* {name}\n"
                f"📦 *Granted Services:* {apps_display}\n"
                f"⏳ *Valid For:* {days} day{'s' if days != 1 else ''}\n\n"
                f"🔗 *Invite Link:*\n{invite_res.invite_url}\n\n"
                f"_Forward this link to {name} to complete their setup._"
            )
        except Exception as e:
            logger.error(f"Error creating invite from bot: {e}")
            return f"❌ Failed to create invitation: {str(e)}"

    async def process_message(self, sender: str, raw_message: str, channel: str = "whatsapp") -> Optional[str]:
        """
        Processes incoming WhatsApp or Telegram message and returns bot response if it is a command.
        """
        message = raw_message.strip()
        if not (message.startswith("!") or message.startswith("/")):
            return None

        # Check authorization based on channel
        if channel == "telegram":
            tg_chat_id = sender.replace("tg_", "")
            if not self.is_admin_telegram_chat(tg_chat_id):
                return (
                    "⛔ *Unauthorized*\n\n"
                    f"Your Telegram Chat ID is: `{tg_chat_id}`\n\n"
                    "To authorize this chat to manage Authentik, add this ID in the web dashboard:\n"
                    "👉 *Admin & Settings > Telegram Admin Chat IDs*"
                )
        else:
            if not self.is_admin_phone(sender):
                logger.warning(f"Unauthorized bot command attempt from phone: {sender}")
                configured = settings_service._admin_phone_numbers
                if not configured or not configured.strip():
                    return (
                        "⚠️ *Authentik Bot Disabled*\n\n"
                        "No authorized admin phone numbers have been configured in Authentik Manager.\n"
                        "Please configure your phone number in Settings > WhatsApp Admin Phones."
                    )
                return (
                    f"⛔ *Unauthorized*\n\n"
                    f"Your phone number (+{sender}) is not authorized to issue Authentik Manager commands."
                )

        try:
            tokens = shlex.split(message)
        except Exception:
            tokens = message.split()

        if not tokens:
            return None

        cmd = tokens[0].lower().lstrip("!").lstrip("/")

        if cmd in ("help", "start", "menu"):
            return self.handle_help(channel=channel)
        elif cmd in ("status", "health", "info"):
            return await self.handle_status()
        elif cmd in ("presets", "templates"):
            return await self.handle_presets()
        elif cmd in ("invite", "add", "new"):
            return await self.handle_invite(sender, tokens, channel=channel)
        else:
            return f"❓ Unknown command `/{cmd}`. Type `/{'help'}` for available commands."

bot_service = BotService()
