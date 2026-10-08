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
    authentik_client._init_mock_store()
    settings.DEMO_MODE = False
    settings.AUTH_METHOD = "password"
    settings.ADMIN_PASSWORD = "CorrectTestPassword123!"
    settings_service._admin_password_hash = None
    
    await init_db()
    from app.security import hash_password
    hashed = hash_password("CorrectTestPassword123!")
    from app.database import set_app_setting
    await set_app_setting("auth_method", "password")
    await set_app_setting("admin_password_hash", hashed, is_secret=True)
    await settings_service.load_settings_into_runtime()

    # Reset in-memory trackers before each test
    from app.security import _ip_login_attempts, _global_login_attempts, _revoked_jtis
    _ip_login_attempts.clear()
    _global_login_attempts.clear()
    _revoked_jtis.clear()

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

    # Now any IP is throttled
    assert is_login_rate_limited("10.0.0.99") is True

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
