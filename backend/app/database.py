import os
import json
import aiosqlite
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import settings

def get_db_path() -> str:
    db_path = settings.SQLITE_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    return db_path

async def init_db():
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_name TEXT NOT NULL,
                target_id TEXT,
                details TEXT,
                status TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitation_pk TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                whatsapp_sent INTEGER DEFAULT 0,
                expires_at TEXT,
                single_use INTEGER DEFAULT 1,
                assigned_groups TEXT NOT NULL, -- JSON array of group PKs
                assigned_apps TEXT NOT NULL,   -- JSON array of app names
                invite_url TEXT NOT NULL,
                status TEXT NOT NULL,          -- 'pending', 'redeemed', 'expired'
                redeemed_by TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS expiring_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_pk INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                app_pk TEXT NOT NULL,
                app_name TEXT NOT NULL,
                group_pk TEXT NOT NULL,
                role TEXT NOT NULL, -- 'member' | 'admin'
                expires_at TEXT NOT NULL, -- ISO 8601 string
                created_at TEXT NOT NULL,
                is_revoked INTEGER DEFAULT 0,
                UNIQUE(user_pk, app_pk, group_pk)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS access_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                icon TEXT DEFAULT 'shield',
                assignments TEXT NOT NULL, -- JSON string of { app_slug_or_pk: role }
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                is_secret INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Safely migrate existing databases if columns do not exist
        for col, col_type in [("phone", "TEXT"), ("whatsapp_sent", "INTEGER DEFAULT 0")]:
            try:
                await db.execute(f"ALTER TABLE tracked_invites ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        
        # Seed default templates if table is empty
        async with db.execute("SELECT COUNT(*) FROM access_templates") as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                defaults = [
                    (
                        "Household Member",
                        "Standard member access to household applications (Home Assistant, Media, Bookstack, Bar Assistant)",
                        "home",
                        json.dumps({"*": "member"}),
                        now
                    ),
                    (
                        "Guest / Visitor",
                        "Temporary leisure and visitor services (Bar Assistant, Guest Portal)",
                        "users",
                        json.dumps({"bar-assistant": "member"}),
                        now
                    ),
                    (
                        "Homelab Admin",
                        "Full administrative control across all applications",
                        "crown",
                        json.dumps({"*": "admin"}),
                        now
                    )
                ]
                await db.executemany(
                    "INSERT INTO access_templates (name, description, icon, assignments, created_at) VALUES (?, ?, ?, ?, ?)",
                    defaults
                )

        # Migration: Purge legacy non-existent keys (e.g. 'guest-wifi') from existing access_templates
        try:
            async with db.execute("SELECT id, assignments FROM access_templates") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    t_id = row[0]
                    raw_assign = row[1]
                    try:
                        assign_dict = json.loads(raw_assign) if raw_assign else {}
                        if "guest-wifi" in assign_dict:
                            del assign_dict["guest-wifi"]
                            await db.execute(
                                "UPDATE access_templates SET assignments = ? WHERE id = ?",
                                (json.dumps(assign_dict), t_id)
                            )
                    except Exception:
                        pass
        except Exception:
            pass

        await db.commit()

# --- Audit Logs ---

async def record_audit_log(
    actor: str,
    action: str,
    target_type: str,
    target_name: str,
    target_id: Optional[str] = None,
    details: Optional[str] = None,
    status: str = "SUCCESS"
):
    db_path = get_db_path()
    timestamp = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO audit_logs (timestamp, actor, action, target_type, target_name, target_id, details, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, actor, action, target_type, target_name, target_id or "", details or "", status)
        )
        await db.commit()

async def get_audit_logs(limit: int = 100) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

# --- Expiring Grants (Leases) ---

async def save_expiring_grant(
    user_pk: int,
    user_name: str,
    app_pk: str,
    app_name: str,
    group_pk: str,
    role: str,
    expires_at: str
) -> Dict[str, Any]:
    db_path = get_db_path()
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO expiring_grants (user_pk, user_name, app_pk, app_name, group_pk, role, expires_at, created_at, is_revoked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_pk, app_pk, group_pk) DO UPDATE SET
                expires_at = excluded.expires_at,
                role = excluded.role,
                is_revoked = 0
            """,
            (user_pk, user_name, app_pk, app_name, group_pk, role, expires_at, now)
        )
        await db.commit()
    return {
        "user_pk": user_pk,
        "user_name": user_name,
        "app_pk": app_pk,
        "app_name": app_name,
        "group_pk": group_pk,
        "role": role,
        "expires_at": expires_at,
        "created_at": now,
        "is_revoked": False,
    }

async def revoke_expiring_grant(user_pk: int, app_pk: str, group_pk: str):
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE expiring_grants SET is_revoked = 1 WHERE user_pk = ? AND app_pk = ? AND group_pk = ?",
            (user_pk, app_pk, group_pk)
        )
        await db.commit()

async def get_active_expiring_grants() -> List[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM expiring_grants WHERE is_revoked = 0"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_due_expiring_grants(now_iso: str) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM expiring_grants WHERE is_revoked = 0 AND expires_at <= ?",
            (now_iso,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def mark_grant_revoked(grant_id: int):
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE expiring_grants SET is_revoked = 1 WHERE id = ?", (grant_id,))
        await db.commit()

# --- Access Templates ---

async def get_access_templates() -> List[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM access_templates ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                try:
                    item["assignments"] = json.loads(item["assignments"])
                except Exception:
                    item["assignments"] = {}
                result.append(item)
            return result

async def get_access_template(template_id: int) -> Optional[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM access_templates WHERE id = ?", (template_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["assignments"] = json.loads(item["assignments"])
            except Exception:
                item["assignments"] = {}
            return item

async def save_access_template(name: str, description: Optional[str], icon: str, assignments: Dict[str, str]) -> Dict[str, Any]:
    db_path = get_db_path()
    now = datetime.now(timezone.utc).isoformat()
    clean_assignments = {k: v for k, v in (assignments or {}).items() if k != "guest-wifi" and v in ("member", "admin", "user")}
    assign_json = json.dumps(clean_assignments)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO access_templates (name, description, icon, assignments, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                icon = excluded.icon,
                assignments = excluded.assignments
            RETURNING id
            """,
            (name, description or "", icon or "shield", assign_json, now)
        )
        row = await cursor.fetchone()
        template_id = row[0]
        await db.commit()
    return {
        "id": template_id,
        "name": name,
        "description": description,
        "icon": icon,
        "assignments": clean_assignments,
        "created_at": now,
    }

async def update_access_template(
    template_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    icon: Optional[str] = None,
    assignments: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    db_path = get_db_path()
    existing = await get_access_template(template_id)
    if not existing:
        return None

    new_name = name.strip() if name is not None and name.strip() else existing["name"]
    new_desc = description if description is not None else existing.get("description", "")
    new_icon = icon.strip() if icon is not None and icon.strip() else existing.get("icon", "shield")
    raw_assignments = assignments if assignments is not None else existing.get("assignments", {})
    clean_assignments = {k: v for k, v in (raw_assignments or {}).items() if k != "guest-wifi" and v in ("member", "admin", "user")}
    assign_json = json.dumps(clean_assignments)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE access_templates
            SET name = ?, description = ?, icon = ?, assignments = ?
            WHERE id = ?
            """,
            (new_name, new_desc, new_icon, assign_json, template_id)
        )
        await db.commit()

    return {
        "id": template_id,
        "name": new_name,
        "description": new_desc,
        "icon": new_icon,
        "assignments": clean_assignments,
        "created_at": existing["created_at"],
    }

async def delete_access_template(template_id: int) -> bool:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("DELETE FROM access_templates WHERE id = ?", (template_id,))
        await db.commit()
        return cursor.rowcount > 0

# --- App Settings ---

async def get_all_app_settings() -> Dict[str, Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM app_settings") as cursor:
            rows = await cursor.fetchall()
            return {row["key"]: dict(row) for row in rows}

async def get_app_setting(key: str) -> Optional[Dict[str, Any]]:
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM app_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_app_setting(key: str, value: str, is_secret: bool = False):
    db_path = get_db_path()
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO app_settings (key, value, is_secret, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                is_secret = excluded.is_secret,
                updated_at = excluded.updated_at
            """,
            (key, value, 1 if is_secret else 0, now)
        )
        await db.commit()
