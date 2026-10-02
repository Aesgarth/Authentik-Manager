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

@pytest.mark.asyncio
async def test_settings_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get settings
        get_res = await client.get("/api/settings")
        assert get_res.status_code == 200
        data = get_res.json()
        assert "authentik_url" in data
        assert "app_group_prefix" in data

        # Update settings with a secret token
        put_res = await client.put(
            "/api/settings",
            json={
                "authentik_url": "https://auth.company.test",
                "authentik_token": "super_secret_test_token_12345",
                "app_group_prefix": "Secured - ",
                "default_country_code": "1",
                "default_lease_duration_hours": 48
            }
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["authentik_url"] == "https://auth.company.test"
        assert updated["app_group_prefix"] == "Secured - "
        assert updated["default_country_code"] == "1"
        assert updated["default_lease_duration_hours"] == 48
        # Token should be masked in response
        assert updated["authentik_token_masked"].startswith("••••••••")
        assert updated["authentik_token_configured"] is True

        # Verify token in SQLite is encrypted, not raw plaintext
        from app.database import get_app_setting
        row = await get_app_setting("authentik_token")
        assert row is not None
        assert row["is_secret"] == 1
        assert "super_secret_test_token_12345" not in row["value"]

        # Verify test authentik connection endpoint
        test_res = await client.post(
            "/api/settings/test-authentik",
            json={
                "url": "https://auth.company.test",
                "token": "super_secret_test_token_12345"
            }
        )
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert "success" in test_data

@pytest.mark.asyncio
async def test_csv_export():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/matrix/export/csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        csv_text = res.text
        assert "Username,Email,Role,Last Login" in csv_text
        assert "guest_charlie" in csv_text
        assert "alex" in csv_text

@pytest.mark.asyncio
async def test_notification_and_bot_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test notification endpoint
        notif_res = await client.post("/api/settings/test-notification", json={"channel": "all"})
        assert notif_res.status_code == 200
        assert "results" in notif_res.json()

        # 2. Test bot command from unauthorized phone
        unauth_res = await client.post(
            "/api/whatsapp/bot-command",
            json={"sender": "447999888777", "message": "!status"}
        )
        assert unauth_res.status_code == 200
        unauth_data = unauth_res.json()
        assert "Unauthorized" in unauth_data["reply"] or "Disabled" in unauth_data["reply"]

        # 3. Configure admin phone number
        await client.put(
            "/api/settings",
            json={"admin_phone_numbers": "+44 7999 888 777"}
        )

        # 4. Test !help
        help_res = await client.post(
            "/api/whatsapp/bot-command",
            json={"sender": "447999888777", "message": "!help"}
        )
        assert help_res.status_code == 200
        assert "Available Commands" in help_res.json()["reply"]

        # 5. Test !status
        status_res = await client.post(
            "/api/whatsapp/bot-command",
            json={"sender": "447999888777", "message": "!status"}
        )
        assert status_res.status_code == 200
        assert "Authentik Manager Status" in status_res.json()["reply"]

        # 6. Test !presets
        presets_res = await client.post(
            "/api/whatsapp/bot-command",
            json={"sender": "447999888777", "message": "!presets"}
        )
        assert presets_res.status_code == 200
        assert "Available Access Presets" in presets_res.json()["reply"] or "No access presets" in presets_res.json()["reply"]

        # 7. Test !invite
        invite_res = await client.post(
            "/api/whatsapp/bot-command",
            json={"sender": "447999888777", "message": "!invite John Jellyfin 5"}
        )
        assert invite_res.status_code == 200
        inv_data = invite_res.json()
        assert "Invitation Generated" in inv_data["reply"]
        assert "John" in inv_data["reply"]
        assert "itoken=" in inv_data["reply"]

@pytest.mark.asyncio
async def test_telegram_integration():
    from app.services.bot_service import bot_service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test test-telegram endpoint with empty token
        tg_test_res = await client.post("/api/settings/test-telegram", json={})
        assert tg_test_res.status_code == 200
        assert tg_test_res.json()["success"] is False

        # 2. Update Telegram settings
        put_res = await client.put(
            "/api/settings",
            json={
                "telegram_enabled": True,
                "telegram_bot_token": "1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234",
                "telegram_admin_chat_ids": "99887766, 55443322"
            }
        )
        assert put_res.status_code == 200
        settings_data = put_res.json()
        assert settings_data["telegram_enabled"] is True
        assert settings_data["telegram_bot_token_configured"] is True
        assert settings_data["telegram_bot_token_masked"].startswith("••••••••")
        assert "99887766" in settings_data["telegram_admin_chat_ids"]

        # 3. Test unauthorized Telegram chat ID
        unauth_reply = await bot_service.process_message(
            sender="112233",
            raw_message="/status",
            channel="telegram"
        )
        assert "Unauthorized" in unauth_reply
        assert "112233" in unauth_reply

        # 4. Test authorized Telegram /help
        help_reply = await bot_service.process_message(
            sender="99887766",
            raw_message="/help",
            channel="telegram"
        )
        assert "Available Commands" in help_reply
        assert "/status" in help_reply

        # 5. Test authorized Telegram /status
        status_reply = await bot_service.process_message(
            sender="99887766",
            raw_message="/status",
            channel="telegram"
        )
        assert "Authentik Manager Status" in status_reply

        # 6. Test authorized Telegram /invite
        invite_reply = await bot_service.process_message(
            sender="99887766",
            raw_message="/invite Lisa Jellyfin 7",
            channel="telegram"
        )
        assert "Invitation Generated" in invite_reply
        assert "Lisa" in invite_reply
        assert "itoken=" in invite_reply

@pytest.mark.asyncio
async def test_oidc_auto_setup():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test URL detection endpoint
        det_res = await client.get("/api/settings/detect-url")
        assert det_res.status_code == 200
        det_data = det_res.json()
        assert "detected_url" in det_data
        assert "redirect_uri" in det_data

        # 2. Execute 1-Click OIDC Auto-Setup
        setup_payload = {
            "app_url": "https://auth-manager.homelab.lan",
            "app_name": "Authentik Access Manager",
            "app_slug": "authentik-manager",
            "admin_group_name": "authentik Admins",
            "activate_immediately": True
        }
        setup_res = await client.post("/api/settings/auto-setup-oidc", json=setup_payload)
        assert setup_res.status_code == 200
        setup_data = setup_res.json()
        assert setup_data["success"] is True
        assert setup_data["app_url"] == "https://auth-manager.homelab.lan"
        assert setup_data["redirect_uri"] == "https://auth-manager.homelab.lan/api/auth/oidc/callback"
        assert setup_data["application_slug"] == "authentik-manager"
        assert setup_data["bound_group_name"] == "authentik Admins"
        assert setup_data["auth_method"] == "oidc"
        assert len(setup_data["steps_completed"]) >= 5

        # 3. Verify settings were persisted and updated in runtime
        settings_res = await client.get("/api/settings")
        assert settings_res.status_code == 200
        s_data = settings_res.json()
        assert s_data["auth_method"] == "oidc"
        assert s_data["app_url"] == "https://auth-manager.homelab.lan"
        assert s_data["oidc_configured"] is True
        assert s_data["oidc_client_id"].startswith("authentik-manager-")
        assert s_data["oidc_redirect_uri"] == "https://auth-manager.homelab.lan/api/auth/oidc/callback"

        # 4. Verify auth status
        auth_res = await client.get("/api/auth/status")
        assert auth_res.status_code == 200
        auth_data = auth_res.json()
        assert auth_data["auth_method"] == "oidc"

        # 5. Verify OIDC login initiates redirect
        login_res = await client.get("/api/auth/oidc/login", follow_redirects=False)
        assert login_res.status_code in (302, 307)
        assert "application/o/authorize" in login_res.headers["location"]
        assert "client_id=" in login_res.headers["location"]
        assert "redirect_uri=" in login_res.headers["location"]

@pytest.mark.asyncio
async def test_install_flow_policy_and_sync():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test install policy
        install_res = await client.post("/api/invites/install-policy")
        assert install_res.status_code == 200
        data = install_res.json()
        assert data["status"] in ("success", "warning")

        # Test sync endpoint
        sync_res = await client.post("/api/invites/sync")
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["status"] == "ok"
        assert "redeemed_count" in sync_data






