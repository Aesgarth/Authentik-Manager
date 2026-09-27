from fastapi import APIRouter
from app.config import settings
from app.models import HealthResponse
from app.authentik_client import authentik_client
from app.services.matrix_service import matrix_service
from app.services.invite_service import invite_service

router = APIRouter(prefix="/api/health", tags=["Health & Stats"])

@router.get("", response_model=HealthResponse)
async def get_health():
    is_connected = await authentik_client.test_connection()
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

    return HealthResponse(
        status="healthy" if is_connected else "degraded",
        authentik_connected=is_connected,
        authentik_url=settings.AUTHENTIK_URL,
        demo_mode=settings.DEMO_MODE,
        auth_method=settings.AUTH_METHOD,
        total_users=total_users,
        total_apps=total_apps,
        unprotected_apps_count=unprotected_count,
        active_invites_count=active_invites,
    )
