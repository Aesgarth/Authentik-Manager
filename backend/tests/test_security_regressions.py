import os
import time
import pytest
import pytest_asyncio
import jwt
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.database import init_db, record_revoked_token, get_all_active_revoked_jtis
from app.authentik_client import authentik_client
from app.services.settings_service import settings_service
from app.security import (
    resolve_secret_key,
    is_login_rate_limited,
    record_failed_login,
    reset_login_attempts,
    validate_external_url,
    is_jwt_revoked,
    sync_revoked_jtis,
)
from app.auth import create_access_token

@pytest_asyncio.fixture(autouse=True)
async def setup_test_environment(tmp_path):
    test_db = str(tmp_path / "test_sec.db")
    settings.SQLITE_DB_PATH = test_db
    authentik_client.demo_mode = True
    authentik_client._init_mock_store()
    settings.DEMO_MODE = False
    settings.AUTH_METHOD = "password"
    settings.AUTHENTIK_URL = "http://localhost:9000"
    settings.ADMIN_PASSWORD = "CorrectTestPassword123!"
    settings_service._admin_password_hash = None
    settings_service._session_epoch = 0.0
    
    await init_db()
    from app.security import hash_password
    hashed = hash_password("CorrectTestPassword123!")
    from app.database import set_app_setting
    await set_app_setting("auth_method", "password")
    await set_app_setting("admin_password_hash", hashed, is_secret=True)
    await set_app_setting("session_epoch", "0")
    await settings_service.load_settings_into_runtime()

    # Reset in-memory trackers before each test
    from app.security import _ip_login_attempts, _global_login_attempts, _revoked_jtis
    _ip_login_attempts.clear()
    _global_login_attempts.clear()
    _revoked_jtis.clear()
    from app.routers.webhooks import _failed_webhook_attempts
    _failed_webhook_attempts.clear()

@pytest.mark.asyncio
async def test_f1_login_lockout_and_untrusted_forwarded_for():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 5 wrong attempts from the same direct IP triggers 429
        for i in range(5):
            res = await client.post("/api/auth/login", json={"password": f"wrong-pass-{i}"})
            assert res.status_code == 401

        # 6th attempt should be rate limited
        locked_res = await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})
        assert locked_res.status_code == 429
        assert "Too many failed login attempts" in locked_res.json()["detail"]

        # Reset attempts for next check
        reset_login_attempts("127.0.0.1")
        reset_login_attempts("testclient")

        # 2. Test spoofing X-Forwarded-For from an untrusted direct host
        # Default trusted proxies is "127.0.0.1,::1". A client connecting from 192.168.1.50 is untrusted.
        # Its X-Forwarded-For must be ignored and the direct socket IP used instead.
        from app.auth import get_client_ip
        from starlette.requests import Request

        scope_untrusted = {
            "type": "http",
            "client": ("192.168.1.50", 12345),
            "headers": [(b"x-forwarded-for", b"8.8.8.8")],
        }
        req_untrusted = Request(scope_untrusted)
        assert get_client_ip(req_untrusted) == "192.168.1.50"

        # Direct connection from trusted loopback DOES trust XFF
        scope_trusted = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.195")],
        }
        req_trusted = Request(scope_trusted)
        assert get_client_ip(req_trusted) == "203.0.113.195"

@pytest.mark.asyncio
async def test_f1_global_lockout_against_rotating_ips():
    # If an attacker rotates 20 different IPs with wrong passwords, global lockout triggers
    for i in range(20):
        record_failed_login(f"198.51.100.{i}")

    # Remote IP is throttled
    assert is_login_rate_limited("10.0.0.99") is True

    # Local admin loopback is exempt from global DoS lockout (G1 mitigation)
    assert is_login_rate_limited("127.0.0.1") is False

    # Resetting on successful login clears global lockout
    reset_login_attempts("10.0.0.99")
    assert is_login_rate_limited("10.0.0.99") is False

@pytest.mark.asyncio
async def test_f2_settings_saves_in_password_mode():
    transport = ASGITransport(app=app)
    # Log in first to get valid session
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/auth/login",
            json={"password": "CorrectTestPassword123!"}
        )
        assert login_res.status_code == 200

        # 1. Saving settings with existing unchanged authentik_url & auth_method does NOT require current_password
        save_noop = await client.put(
            "/api/settings",
            json={
                "authentik_url": settings.AUTHENTIK_URL,
                "auth_method": settings.AUTH_METHOD,
                "whatsapp_enabled": True,
                "default_country_code": "44"
            }
        )
        assert save_noop.status_code == 200
        assert save_noop.json()["authentik_url"] == settings.AUTHENTIK_URL

        # 2. Changing sensitive authentik_url WITHOUT current_password returns 403
        save_url_no_pw = await client.put(
            "/api/settings",
            json={
                "authentik_url": "https://new-authentik.company.lan",
                "auth_method": "password"
            }
        )
        assert save_url_no_pw.status_code == 403
        assert "Current administrator password is required" in save_url_no_pw.json()["detail"]

        # 3. Changing sensitive authentik_url with INCORRECT current_password returns 403
        save_url_bad_pw = await client.put(
            "/api/settings",
            json={
                "authentik_url": "https://new-authentik.company.lan",
                "current_password": "WrongPassword999!"
            }
        )
        assert save_url_bad_pw.status_code == 403

        # 4. Changing sensitive authentik_url WITH CORRECT current_password returns 200
        save_url_ok = await client.put(
            "/api/settings",
            json={
                "authentik_url": "https://new-authentik.company.lan",
                "current_password": "CorrectTestPassword123!"
            }
        )
        assert save_url_ok.status_code == 200
        assert settings.AUTHENTIK_URL == "https://new-authentik.company.lan"

@pytest.mark.asyncio
async def test_f4_initial_admin_password_cleanup(tmp_path):
    data_dir = os.path.dirname(settings.SQLITE_DB_PATH) or "data"
    os.makedirs(data_dir, exist_ok=True)
    pw_file = os.path.join(data_dir, ".initial_admin_password")

    # Write a dummy initial password file
    with open(pw_file, "w", encoding="utf-8") as f:
        f.write("temporary-init-pw")
    assert os.path.exists(pw_file)

    # Logging in with correct password should delete the file
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})
        assert res.status_code == 200
        assert not os.path.exists(pw_file)

    # Re-create and verify password update via settings also deletes it
    with open(pw_file, "w", encoding="utf-8") as f:
        f.write("temporary-init-pw-2")
    assert os.path.exists(pw_file)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})
        update_res = await client.put(
            "/api/settings",
            json={
                "admin_password": "BrandNewAdminPassword456!",
                "current_password": "CorrectTestPassword123!"
            }
        )
        assert update_res.status_code == 200
        assert not os.path.exists(pw_file)

@pytest.mark.asyncio
async def test_f5_secret_key_file_permissions(tmp_path):
    temp_data = str(tmp_path / "data")
    key = resolve_secret_key("", data_dir=temp_data)
    assert len(key) >= 32
    key_path = os.path.join(temp_data, ".secret_key")
    assert os.path.exists(key_path)

    # On POSIX systems, verify mode 0600 (on Windows chmod only toggles read-only, check gracefully)
    if hasattr(os, "stat") and os.name != "nt":
        mode = oct(os.stat(key_path).st_mode & 0o777)
        assert mode == "0o600"

@pytest.mark.asyncio
async def test_f6_session_revocation_persistence():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Log in
        login_res = await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})
        assert login_res.status_code == 200
        token = client.cookies.get("session_token")
        assert token is not None

        # Confirm token works
        status_res = await client.get("/api/auth/status")
        assert status_res.status_code == 200
        assert status_res.json()["authenticated"] is True

        # Log out
        logout_res = await client.post("/api/auth/logout")
        assert logout_res.status_code == 200

        # Decode token to inspect jti
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        jti = payload["jti"]
        assert is_jwt_revoked(jti) is True

        # Check token is in persistent SQLite table
        active_jtis = await get_all_active_revoked_jtis()
        assert jti in active_jtis

        # Reuse revoked token via header -> returns 401 Session has been revoked
        reused_res = await client.get(
            "/api/auth/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Auth status endpoint returns authenticated=False on 401
        assert reused_res.json()["authenticated"] is False

        # Attempt to access protected endpoint with revoked token
        protected_res = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert protected_res.status_code == 401
        assert "Session has been revoked" in protected_res.json()["detail"]

        # Simulate server restart by clearing memory and syncing from DB
        from app.security import _revoked_jtis
        _revoked_jtis.clear()
        assert not is_jwt_revoked(jti)

        # Hydrate from DB
        synced = await get_all_active_revoked_jtis()
        sync_revoked_jtis(synced)
        assert is_jwt_revoked(jti) is True

@pytest.mark.asyncio
async def test_ssrf_validation_cases():
    # Cloud metadata IPs and hostnames
    assert validate_external_url("http://169.254.169.254")[0] is False
    assert validate_external_url("http://metadata.google.internal")[0] is False
    assert validate_external_url("http://instance-data")[0] is False

    # Decimal & Hex encoded IP bypasses
    assert validate_external_url("http://2852039166")[0] is False # 169.254.169.254
    assert validate_external_url("http://0xa9fea9fe")[0] is False
    assert validate_external_url("http://0xa9.0xfe.0xa9.0xfe")[0] is False

    # Invalid schemes
    assert validate_external_url("ftp://authentik.lan")[0] is False
    assert validate_external_url("gopher://authentik.lan")[0] is False

    # Valid URLs
    assert validate_external_url("https://auth.company.com")[0] is True
    assert validate_external_url("http://192.168.1.100:9000")[0] is True

@pytest.mark.asyncio
async def test_forged_jwt_with_legacy_placeholder_keys():
    transport = ASGITransport(app=app)
    legacy_keys = [
        "changeme-in-production-use-a-strong-secret-key-32chars",
        "change-this-to-a-random-32-character-secret-key",
        "secret",
        "admin123"
    ]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for leg_key in legacy_keys:
            forged_token = jwt.encode(
                {"sub": "admin", "name": "Forged", "is_admin": True, "exp": time.time() + 3600},
                leg_key,
                algorithm="HS256"
            )
            res = await client.get("/api/users", headers={"Authorization": f"Bearer {forged_token}"})
            assert res.status_code == 401

@pytest.mark.asyncio
async def test_g2_outbound_url_protection_and_bridge_secret_leak_prevention():
    from app.services.whatsapp_service import whatsapp_service

    # 1. Verify WhatsApp bridge secret is NOT leaked to untrusted external hosts
    whatsapp_service._initial_origin = "127.0.0.1:3001"
    whatsapp_service.base_url = "http://127.0.0.1:3001"
    assert "X-Bridge-Secret" in whatsapp_service._get_headers()

    # Changing to external host omits the bridge secret
    whatsapp_service.base_url = "http://attacker.local:9999"
    assert "X-Bridge-Secret" not in whatsapp_service._get_headers()
    whatsapp_service.base_url = "http://127.0.0.1:3001"

    # 2. In password mode, changing outbound URLs without current_password is gated (returns 403)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Log in first
        await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})

        # Changing whatsapp_service_url without password returns 403
        wa_res = await client.put(
            "/api/settings",
            json={"whatsapp_service_url": "http://127.0.0.1:3002"}
        )
        assert wa_res.status_code == 403
        assert "Current administrator password is required" in wa_res.json()["detail"]

        # Changing notification_webhook_url without password returns 403
        notif_res = await client.put(
            "/api/settings",
            json={"notification_webhook_url": "https://discord.com/api/webhooks/test"}
        )
        assert notif_res.status_code == 403

        # Changing with current_password succeeds with 200
        ok_res = await client.put(
            "/api/settings",
            json={
                "whatsapp_service_url": "http://127.0.0.1:3002",
                "current_password": "CorrectTestPassword123!"
            }
        )
        assert ok_res.status_code == 200
        assert settings.WHATSAPP_SERVICE_URL == "http://127.0.0.1:3002"

@pytest.mark.asyncio
async def test_authentik_pagination_with_integer_next():
    # Test _get_all_paginated handles Authentik DRF {"pagination": {"next": 2}} integer page numbers
    page_responses = {
        1: {
            "pagination": {"next": 2, "count": 3},
            "results": [{"pk": 101, "name": "Item 1"}]
        },
        2: {
            "pagination": {"next": 3, "count": 3},
            "results": [{"pk": 102, "name": "Item 2"}]
        },
        3: {
            "pagination": {"next": 0, "count": 3},
            "results": [{"pk": 103, "name": "Item 3"}]
        }
    }

    async def mock_request(method, endpoint, params=None):
        page = (params or {}).get("page", 1)
        return page_responses.get(page, {"pagination": {"next": 0}, "results": []})

    original_request = authentik_client._request
    authentik_client._request = mock_request
    try:
        items = await authentik_client._get_all_paginated("/api/v3/core/users/")
        assert len(items) == 3
        assert [i["pk"] for i in items] == [101, 102, 103]
    finally:
        authentik_client._request = original_request

@pytest.mark.asyncio
async def test_invite_repair_does_not_strip_human_users_with_substring_names():
    from app.services.invite_service import invite_service
    import aiosqlite
    from app.database import get_db_path

    # Human user with substring 'bot' in username/name (e.g. Abbott, Talbot, Botha)
    human_user = {
        "pk": 42,
        "username": "talbot",
        "name": "Alex Talbot",
        "email": "talbot@example.com",
        "type": "internal",
        "is_active": True
    }
    all_users = [human_user]
    human_users = [human_user]

    # Seed redeemed invite in SQLite
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO tracked_invites (
                invitation_pk, name, email, phone, whatsapp_sent, expires_at, single_use,
                assigned_groups, assigned_apps, invite_url, status, redeemed_by, created_at
            ) VALUES ('inv-42', 'Talbot Invite', 'talbot@example.com', '', 0, '', 1,
                      '["grp-1"]', '["App"]', 'http://invite', 'redeemed', 'talbot (#42)', '2026-10-01T00:00:00Z')
            """
        )
        await db.commit()

    # Run auto-repair
    repaired = await invite_service._repair_misassigned_invites(human_users, all_users)
    assert repaired == 0

    # Ensure invite remains redeemed and was NOT stripped/reset
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT status, redeemed_by FROM tracked_invites WHERE invitation_pk = 'inv-42'") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "redeemed"
            assert row[1] == "talbot (#42)"

@pytest.mark.asyncio
async def test_session_invalidation_on_password_change():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Log in with current password
        login_res = await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})
        assert login_res.status_code == 200

        # Session token is valid
        auth_check = await client.get("/api/auth/status")
        assert auth_check.status_code == 200
        assert auth_check.json()["authenticated"] is True

        # 2. Change administrator password
        # Sleep slightly so epoch > token iat
        time.sleep(0.05)
        ch_res = await client.put(
            "/api/settings",
            json={
                "admin_password": "NewStrongPassword456!",
                "current_password": "CorrectTestPassword123!"
            }
        )
        assert ch_res.status_code == 200

        # 3. Old session token must now be rejected with 401 on protected endpoint
        expired_check = await client.get("/api/users")
        assert expired_check.status_code == 401
        assert "Session has expired due to administrator password change" in expired_check.json()["detail"]

        # 4. Login with new password succeeds
        login_new = await client.post("/api/auth/login", json={"password": "NewStrongPassword456!"})
        assert login_new.status_code == 200

@pytest.mark.asyncio
async def test_webhook_rate_limiting_and_query_token_behavior():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger 10 failed webhook requests
        for _ in range(10):
            res = await client.post("/api/webhooks/authentik", json={"invalid": "payload"}, headers={"X-Webhook-Token": "wrong-secret"})
            assert res.status_code == 401

        # 11th request must be throttled with 429
        throttled = await client.post("/api/webhooks/authentik", json={"invalid": "payload"}, headers={"X-Webhook-Token": "wrong-secret"})
        assert throttled.status_code == 429
        assert "Too many failed webhook authentication requests" in throttled.json()["detail"]

@pytest.mark.asyncio
async def test_prevent_deactivating_superusers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Authenticate
        await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})

        # 1. User with is_superuser=True (e.g. alex)
        users = await authentik_client.get_users()
        superuser = next(u for u in users if u.get("is_superuser"))
        superuser["is_active"] = True
        toggle_res = await client.post(f"/api/users/{superuser['pk']}/toggle-active")
        assert toggle_res.status_code == 403
        assert "Cannot deactivate superuser" in toggle_res.json()["detail"]

        # 2. User named akadmin
        akadmin_user = {"pk": 999, "username": "akadmin", "is_superuser": False, "is_active": True}
        authentik_client.mock_users.append(akadmin_user)
        toggle_ak = await client.post("/api/users/999/toggle-active")
        assert toggle_ak.status_code == 403
        assert "Cannot deactivate superuser" in toggle_ak.json()["detail"]

@pytest.mark.asyncio
async def test_phone_update_matches_exact_user_pk():
    import aiosqlite
    from app.database import get_db_path

    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        # Insert invite for user #1 and user #12
        await db.execute(
            """
            INSERT INTO tracked_invites (
                invitation_pk, name, email, phone, whatsapp_sent, expires_at, single_use,
                assigned_groups, assigned_apps, invite_url, status, redeemed_by, created_at
            ) VALUES ('inv-1', 'User 1', 'u1@ex.com', '', 0, '', 1, '[]', '[]', '', 'redeemed', 'User 1 (#1)', '2026-10-01'),
                     ('inv-12', 'User 12', 'u12@ex.com', '', 0, '', 1, '[]', '[]', '', 'redeemed', 'User 12 (#12)', '2026-10-01')
            """
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"password": "CorrectTestPassword123!"})

        # Update phone for user_pk 1
        res = await client.patch("/api/users/1/phone", json={"phone": "+441234567890"})
        assert res.status_code == 200

    # Verify only invite for user #1 was updated, NOT user #12
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT invitation_pk, phone FROM tracked_invites WHERE invitation_pk IN ('inv-1', 'inv-12')") as cursor:
            rows = dict(await cursor.fetchall())
            assert rows["inv-1"] == "+441234567890"
            assert rows["inv-12"] == ""

@pytest.mark.asyncio
async def test_ssrf_extended_cases_0_0_0_0_and_ipv6_metadata():
    # 0.0.0.0
    assert validate_external_url("http://0.0.0.0")[0] is False
    assert validate_external_url("http://0.0.0.0:8000")[0] is False

    # AWS EC2 IPv6 metadata service
    assert validate_external_url("http://[fd00:ec2::254]")[0] is False
    assert validate_external_url("https://[fd00:ec2::254]/latest/meta-data/")[0] is False

@pytest.mark.asyncio
async def test_ipv6_parsing_in_get_client_ip():
    from app.auth import get_client_ip
    from starlette.requests import Request

    # Bracketed IPv6 with port
    scope1 = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"[2001:db8::1]:8080")],
    }
    assert get_client_ip(Request(scope1)) == "2001:db8::1"

    # Plain unbracketed IPv6 without port
    scope2 = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"2001:db8::1")],
    }
    assert get_client_ip(Request(scope2)) == "2001:db8::1"

@pytest.mark.asyncio
async def test_bot_ambiguous_matching_rejected():
    from app.services.bot_service import bot_service

    # Single character 'p' is rejected for ambiguous app matching
    res = await bot_service.handle_invite(
        sender="447123456789",
        tokens=["!invite", "Bob", "p", "7"],
        channel="whatsapp"
    )
    assert "Short abbreviations are not permitted" in res or "Could not find" in res or "Ambiguous" in res

