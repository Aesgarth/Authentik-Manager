import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

from app.config import settings
from app.authentik_client import authentik_client

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    settings.DEMO_MODE = True
    authentik_client.demo_mode = True
    authentik_client._init_mock_store()
    await init_db()

@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["demo_mode"] is True
        assert data["total_users"] > 0
        assert data["total_apps"] > 0

@pytest.mark.asyncio
async def test_matrix_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/matrix")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "apps" in data
        assert "permissions" in data
        assert len(data["users"]) >= 4
        assert len(data["apps"]) >= 5

@pytest.mark.asyncio
async def test_toggle_permission():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Fetch matrix first
        matrix_res = await client.get("/api/matrix")
        matrix_data = matrix_res.json()
        app_item = matrix_data["apps"][0]
        group_pk = matrix_data["app_group_map"][app_item["pk"]]

        # Toggle permission
        toggle_res = await client.post(
            "/api/matrix/toggle",
            json={
                "user_pk": 4, # Charlie guest
                "app_pk": app_item["pk"],
                "group_pk": group_pk,
                "grant": True
            }
        )
        assert toggle_res.status_code == 200
        assert toggle_res.json()["granted"] is True

        # Verify updated matrix
        updated_matrix = (await client.get("/api/matrix")).json()
        assert updated_matrix["permissions"]["4"][app_item["pk"]] is True

@pytest.mark.asyncio
async def test_provision_all_unprotected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/apps/provision-all")
        assert response.status_code == 200
        data = response.json()
        assert "provisioned_count" in data
        assert data["provisioned_count"] >= 1

@pytest.mark.asyncio
async def test_create_and_list_invite():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_res = await client.post(
            "/api/invites",
            json={
                "name": "Test Friend",
                "email": "friend@test.lan",
                "expires_in_days": 3,
                "single_use": True,
                "group_pks": ["g1111111-1111-1111-1111-111111111111"],
                "app_names": ["Jellyfin Media"]
            }
        )
        assert create_res.status_code == 200
        invite_data = create_res.json()
        assert invite_data["name"] == "Test Friend"
        assert "itoken=" in invite_data["invite_url"]

        list_res = await client.get("/api/invites")
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

@pytest.mark.asyncio
async def test_spa_frontend_serving():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "<title>Authentik Access Manager</title>" in response.text
        assert "/assets/" in response.text

@pytest.mark.asyncio
async def test_whatsapp_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/whatsapp/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

@pytest.mark.asyncio
async def test_granular_app_provisioning():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get apps first
        apps_res = await client.get("/api/apps")
        assert apps_res.status_code == 200
        paperless = next(a for a in apps_res.json() if a["slug"] == "paperless")

        # Provision both granular user group and admin group
        prov_res = await client.post(
            "/api/apps/provision",
            json={
                "app_pk": paperless["pk"],
                "create_user_group": True,
                "create_admin_group": True
            }
        )
        assert prov_res.status_code == 200
        prov_data = prov_res.json()
        assert prov_data["user_group_pk"] is not None
        assert prov_data["admin_group_pk"] is not None
        assert "Admin" in prov_data["admin_group_name"]

        # Verify matrix reflects both granular groups
        matrix = (await client.get("/api/matrix")).json()
        updated_paperless = next(a for a in matrix["apps"] if a["pk"] == paperless["pk"])
        assert updated_paperless["has_granular_user_group"] is True
        assert updated_paperless["has_granular_admin_group"] is True
        assert updated_paperless["granular_user_group_pk"] == prov_data["user_group_pk"]
        assert updated_paperless["granular_admin_group_pk"] == prov_data["admin_group_pk"]

@pytest.mark.asyncio
async def test_expiring_grants():
    from app.services.lease_service import lease_service
    from datetime import datetime, timezone, timedelta

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an expiring lease on app
        lease_res = await client.post(
            "/api/matrix/lease",
            json={
                "user_pk": 4, # Charlie guest
                "user_name": "Charlie Guest",
                "app_pk": "a1111111-1111-1111-1111-111111111111",
                "app_name": "Jellyfin",
                "group_pk": "g1111111-1111-1111-1111-111111111111",
                "role": "member",
                "duration_hours": 24
            }
        )
        assert lease_res.status_code == 200
        grant_data = lease_res.json()
        assert grant_data["user_pk"] == 4
        assert grant_data["role"] == "member"
        assert grant_data["expires_at"] is not None

        # Verify matrix includes active lease
        matrix = (await client.get("/api/matrix")).json()
        assert "expiring_grants" in matrix
        assert "4" in matrix["expiring_grants"]
        assert "a1111111-1111-1111-1111-111111111111" in matrix["expiring_grants"]["4"]

        # Test expiration: set expires_at in the past
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        from app.database import save_expiring_grant
        await save_expiring_grant(
            user_pk=4,
            user_name="Charlie Guest",
            app_pk="a1111111-1111-1111-1111-111111111111",
            app_name="Jellyfin",
            group_pk="g1111111-1111-1111-1111-111111111111",
            role="member",
            expires_at=past_iso
        )

        expired_count = await lease_service.check_and_expire_leases()
        assert expired_count >= 1

        # Verify revoked in matrix
        active_leases = await lease_service.get_active_leases_map()
        assert "a1111111-1111-1111-1111-111111111111" not in active_leases.get("4", {})

@pytest.mark.asyncio
async def test_access_templates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List default templates
        list_res = await client.get("/api/templates")
        assert list_res.status_code == 200
        templates = list_res.json()
        assert len(templates) >= 3
        template_names = [t["name"] for t in templates]
        assert "Household Member" in template_names
        assert "Guest / Visitor" in template_names

        # Create custom template
        create_res = await client.post(
            "/api/templates",
            json={
                "name": "Media Consumer",
                "description": "Access to streaming entertainment only",
                "icon": "film",
                "assignments": {
                    "a1111111-1111-1111-1111-111111111111": "member"
                }
            }
        )
        assert create_res.status_code == 200
        created = create_res.json()
        assert created["name"] == "Media Consumer"
        assert created["icon"] == "film"

        # Apply template to a user
        apply_res = await client.post(
            f"/api/templates/{created['id']}/apply",
            json={
                "template_id": created["id"],
                "user_pk": 4,
                "user_name": "Charlie Guest",
                "duration_hours": 48
            }
        )
        assert apply_res.status_code == 200
        apply_data = apply_res.json()
        assert apply_data["applied_count"] >= 1


