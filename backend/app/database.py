import os
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
        # Safely migrate existing databases if columns do not exist
        for col, col_type in [("phone", "TEXT"), ("whatsapp_sent", "INTEGER DEFAULT 0")]:
            try:
                await db.execute(f"ALTER TABLE tracked_invites ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        await db.commit()

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
