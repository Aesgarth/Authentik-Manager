import time
from typing import Optional
from fastapi import APIRouter, Request
from app.config import settings
from app.models import HealthResponse
from app.authentik_client import authentik_client
from app.services.matrix_service import matrix_service
from app.services.invite_service import invite_service
from app.auth import get_current_user

router = APIRouter(prefix="/api/health", tags=["Health & Stats"])

_last_health_cache: Optional[HealthResponse] = None
_last_health_time: float = 0.0
HEALTH_CACHE_TTL = 30.0  # seconds

@router.get("", response_model=HealthResponse)
async def get_health(request: Request):
    # Determine if request is authenticated or in open/demo mode
    is_authenticated = False
    if settings.DEMO_MODE or settings.AUTH_METHOD == "none":
        is_authenticated = True
    else:
        try:
            user = await get_current_user(request)
            if user:
                is_authenticated = True
        except Exception:
            is_authenticated = False

    # Unauthenticated callers (e.g. Docker liveness checks or scanners) receive lightweight status
    if not is_authenticated:
        return HealthResponse(
            status="healthy",
            authentik_connected=True,
            connection_error=None,
            authentik_url="",
            demo_mode=settings.DEMO_MODE,
            auth_method=settings.AUTH_METHOD,
            total_users=0,
            total_apps=0,
            unprotected_apps_count=0,
            active_invites_count=0,
        )

    # For authenticated users, serve from TTL cache to avoid hammering Authentik
    global _last_health_cache, _last_health_time
    now = time.time()
    if _last_health_cache and (now - _last_health_time < HEALTH_CACHE_TTL):
        return _last_health_cache

    is_connected, conn_error = await authentik_client.test_connection()
    try:
        matrix = await matrix_service.get_matrix()
        total_users = len(matrix.users)
        total_apps = len(matrix.apps)
        unprotected_count = len([a for a in matrix.apps if not a.is_protected])
    except Exception:
        total_users = 0
        total_apps = 0
        unprotected_count = 0

    try:
        invites = await invite_service.list_invites()
        active_invites = len([i for i in invites if i.status == "pending"])
    except Exception:
        active_invites = 0

    resp = HealthResponse(
        status="healthy" if is_connected else "degraded",
        authentik_connected=is_connected,
        connection_error=conn_error,
        authentik_url=settings.AUTHENTIK_URL,
        demo_mode=settings.DEMO_MODE,
        auth_method=settings.AUTH_METHOD,
        total_users=total_users,
        total_apps=total_apps,
        unprotected_apps_count=unprotected_count,
        active_invites_count=active_invites,
    )

    _last_health_cache = resp
    _last_health_time = now
    return resp
