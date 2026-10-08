import os
import time
import hmac
import hashlib
import secrets
import logging
import socket
import ipaddress
from typing import Optional
from urllib.parse import urlsplit

logger = logging.getLogger("authentik_manager.security")

# --- Password Hashing (PBKDF2-HMAC-SHA256) ---

def hash_password(password: str) -> str:
    """Hashes a password with PBKDF2-HMAC-SHA256 and 600,000 iterations (OWASP standard)."""
    salt = secrets.token_bytes(16)
    iterations = 600_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${derived.hex()}"

def verify_password(plain_password: str, hashed_or_plain: str) -> bool:
    """
    Verifies a plain password against a stored hash or legacy plaintext string.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not hashed_or_plain or not plain_password:
        return False

    if hashed_or_plain.startswith("pbkdf2:sha256:"):
        try:
            prefix, salt_hex, hash_hex = hashed_or_plain.split("$")
            iterations = int(prefix.split(":")[2])
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(derived, expected)
        except Exception as e:
            logger.warning(f"Error parsing password hash: {e}")
            return False

    # Legacy plaintext fallback (constant-time)
    return secrets.compare_digest(plain_password, hashed_or_plain)

# --- Persistent Secret Key Management ---

DEFAULT_INSECURE_KEYS = {
    "changeme-in-production-use-a-strong-secret-key-32chars",
    "change-this-to-a-random-32-character-secret-key",
    "secret",
    "admin123",
    "",
}

PLACEHOLDER_PASSWORDS = {
    "",
    "admin123",
    "admin",
    "password",
    "change-this-to-a-secure-password",
    "your_secure_password",
}

def is_placeholder_secret_key(key: Optional[str]) -> bool:
    if not key:
        return True
    k = key.strip().lower()
    return (
        k in DEFAULT_INSECURE_KEYS
        or k.startswith("change-this")
        or k.startswith("changeme")
        or k.startswith("your_")
        or len(key.strip()) < 32
    )

def is_insecure_password(pw: Optional[str]) -> bool:
    if not pw:
        return True
    clean = pw.strip().lower()
    return (
        clean in PLACEHOLDER_PASSWORDS
        or clean.startswith("change-this")
        or clean.startswith("changeme")
        or clean.startswith("your_")
        or len(clean) < 6
    )

def resolve_secret_key(configured_key: str, data_dir: str = "data") -> str:
    """
    Ensures a cryptographically secure SECRET_KEY is always used:
    1. If configured_key is provided and not a placeholder (and >= 32 chars), uses it.
    2. Otherwise, looks for a persistent key file in data_dir/.secret_key.
    3. If neither exists, generates a secure random 64-char key and writes it to data_dir/.secret_key.
    """
    clean_key = (configured_key or "").strip()
    if not is_placeholder_secret_key(clean_key):
        return clean_key

    key_file = os.path.join(data_dir, ".secret_key")
    try:
        if os.path.exists(key_file):
            if hasattr(os, "chmod"):
                try:
                    os.chmod(key_file, 0o600)
                except Exception:
                    pass
            with open(key_file, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if len(saved) >= 32 and not is_placeholder_secret_key(saved):
                    return saved
    except Exception as e:
        logger.warning(f"Could not read persistent secret key file {key_file}: {e}")

    # Generate a new persistent key
    generated = secrets.token_hex(32)
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(generated)
        if hasattr(os, "chmod"):
            try:
                os.chmod(key_file, 0o600)
            except Exception:
                pass
        logger.info(f"Generated new secure persistent secret key in {key_file} (mode 0600)")
    except Exception as e:
        logger.warning(f"Could not persist secret key to {key_file}: {e}")

    return generated

# --- Rate Limiting for Login Attempts (Per-IP and Global Lockout) ---

_ip_login_attempts: dict[str, list[float]] = {}
_global_login_attempts: list[float] = []

MAX_IP_LOGIN_ATTEMPTS = 5
MAX_GLOBAL_LOGIN_ATTEMPTS = 20
LOGIN_WINDOW_SECONDS = 300  # 5 minutes

def is_local_admin_ip(client_ip: str) -> bool:
    """Checks if client_ip is loopback (exempt from global remote DoS lockout)."""
    if not client_ip:
        return False
    if client_ip.lower() in ("127.0.0.1", "::1", "localhost"):
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
        return ip.is_loopback
    except ValueError:
        return False

def is_login_rate_limited(client_ip: str) -> bool:
    """
    Checks if login attempts are throttled:
    1. Per-IP: checks if client_ip has exceeded MAX_IP_LOGIN_ATTEMPTS (5) in 5 minutes.
    2. Global: checks if total failed attempts across all IPs exceed MAX_GLOBAL_LOGIN_ATTEMPTS (20) in 5 minutes.
       Prevents brute-forcing the single admin password by rotating X-Forwarded-For or client IPs.
       Localhost / loopback requests are exempt from remote global lockout to prevent denial-of-service against the administrator.
    """
    now = time.time()

    # Clean and check per-IP attempts
    ip_attempts = _ip_login_attempts.get(client_ip, [])
    active_ip = [t for t in ip_attempts if now - t < LOGIN_WINDOW_SECONDS]
    _ip_login_attempts[client_ip] = active_ip
    if len(active_ip) >= MAX_IP_LOGIN_ATTEMPTS:
        return True

    # Loopback / local console access is exempt from global remote DoS lockout
    if is_local_admin_ip(client_ip):
        return False

    # Clean and check global attempts for remote clients
    global _global_login_attempts
    _global_login_attempts = [t for t in _global_login_attempts if now - t < LOGIN_WINDOW_SECONDS]
    if len(_global_login_attempts) >= MAX_GLOBAL_LOGIN_ATTEMPTS:
        return True

    return False

def get_failed_attempt_counts(client_ip: str) -> tuple[int, int]:
    """Returns active (per_ip_count, global_count) within the rate limit window."""
    now = time.time()
    active_ip = len([t for t in _ip_login_attempts.get(client_ip, []) if now - t < LOGIN_WINDOW_SECONDS])
    active_global = len([t for t in _global_login_attempts if now - t < LOGIN_WINDOW_SECONDS])
    return active_ip, active_global

def record_failed_login(client_ip: str) -> None:
    """Records a failed login attempt for both the client_ip and global tracker."""
    now = time.time()
    if client_ip not in _ip_login_attempts:
        _ip_login_attempts[client_ip] = []
    _ip_login_attempts[client_ip].append(now)
    _global_login_attempts.append(now)

def reset_login_attempts(client_ip: str) -> None:
    """Clears failed login attempts upon successful authentication."""
    _ip_login_attempts.pop(client_ip, None)
    _global_login_attempts.clear()

# --- JWT Token Revocation Registry (Bounded & Timestamp-Aware) ---

_revoked_jtis: dict[str, float] = {}

def revoke_jwt_jti(jti: str, expires_at: Optional[float] = None) -> None:
    """Marks a JWT unique token identifier as revoked upon logout with an expiry timestamp."""
    if jti:
        exp = float(expires_at) if expires_at is not None else (time.time() + 86400)
        _revoked_jtis[str(jti)] = exp

def is_jwt_revoked(jti: str) -> bool:
    """Checks if a JWT unique token identifier was revoked, pruning expired records."""
    if not jti:
        return False
    k = str(jti)
    if k in _revoked_jtis:
        if time.time() < _revoked_jtis[k]:
            return True
        else:
            _revoked_jtis.pop(k, None)
    return False

def sync_revoked_jtis(records: dict[str, float]) -> None:
    """Hydrates active revoked tokens from persistent database on startup."""
    now = time.time()
    for k, exp in records.items():
        if exp >= now:
            _revoked_jtis[str(k)] = float(exp)

# --- SSRF and URL Validation ---

METADATA_HOSTNAMES = {
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "100.100.100.200",
}

def is_forbidden_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Identifies cloud metadata, link-local, multicast, or reserved IP addresses."""
    # Check link-local (169.254.0.0/16 and fe80::/10)
    if ip_obj.is_link_local:
        return True
    if ip_obj.is_multicast or ip_obj.is_reserved:
        return True
    # If IPv4-mapped IPv6 (::ffff:169.254.x.x), inspect mapped IPv4
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        if ip_obj.ipv4_mapped.is_link_local or ip_obj.ipv4_mapped.is_reserved:
            return True
    if str(ip_obj) in ("100.100.100.200", "169.254.169.254"):
        return True
    return False

def parse_ip_candidate(hostname: str) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Tries parsing a hostname as an IPv4, IPv6, integer IP, or hex-octet IP."""
    # Standard string parse
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    # Decimal or hex integer IP literal (e.g. 2852039166, 0xa9fea9fe)
    try:
        val = int(hostname, 0)
        return ipaddress.ip_address(val)
    except (ValueError, OverflowError):
        pass

    # Hex octet notation (e.g. 0xa9.0xfe.0xa9.0xfe)
    parts = hostname.split(".")
    if len(parts) == 4 and all(p.startswith("0x") for p in parts):
        try:
            octets = bytes([int(p, 16) for p in parts])
            return ipaddress.IPv4Address(octets)
        except (ValueError, OverflowError):
            pass

    return None

def validate_external_url(url: str, allow_loopback: bool = True) -> tuple[bool, Optional[str]]:
    """
    Validates an external URL for SSRF hazards:
    - Must be http:// or https://
    - Blocks cloud metadata and link-local targets across raw IPs, hex/integer notations, IPv4-mapped IPv6, and DNS resolution.
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"

    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted."

        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            return False, "URL must include a valid hostname"

        if hostname in METADATA_HOSTNAMES or hostname.endswith(".metadata.google.internal"):
            return False, f"Target host '{hostname}' is not permitted."

        # Inspect wildcard DNS services that embed destination IPs (e.g. *.nip.io, *.sslip.io)
        for suffix in (".nip.io", ".sslip.io"):
            if hostname.endswith(suffix):
                prefix = hostname[:-len(suffix)]
                parts = prefix.split(".")
                if len(parts) >= 4:
                    candidate_str = ".".join(parts[-4:])
                    try:
                        emb_ip = ipaddress.ip_address(candidate_str)
                        if is_forbidden_ip(emb_ip):
                            return False, f"Target IP '{emb_ip}' (cloud metadata / link-local) is not permitted."
                        if not allow_loopback and emb_ip.is_loopback:
                            return False, "Target loopback address is not permitted."
                    except ValueError:
                        pass

        # 1. Parse directly if IP literal
        ip_obj = parse_ip_candidate(hostname)
        if ip_obj is not None:
            if is_forbidden_ip(ip_obj):
                return False, f"Target IP '{ip_obj}' (cloud metadata / link-local) is not permitted."
            if not allow_loopback and ip_obj.is_loopback:
                return False, "Target loopback address is not permitted."
            return True, None

        # 2. Hostname is a domain name: resolve DNS to inspect destination IPs
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                res_ip = ipaddress.ip_address(ip_str)
                if is_forbidden_ip(res_ip):
                    return False, f"Target host '{hostname}' resolves to forbidden IP '{res_ip}'."
                if not allow_loopback and res_ip.is_loopback:
                    return False, f"Target host '{hostname}' resolves to loopback IP."
        except socket.gaierror:
            pass

        return True, None
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"

# --- CSV Injection Sanitization ---

def sanitize_csv_cell(val: object) -> str:
    """
    Prevents CSV formula injection in spreadsheet software.
    Prepends a single quote to cells starting with formula trigger characters (=, +, -, @, \\t, \\r).
    """
    s = str(val if val is not None else "")
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s

def safe_compare(candidate: Optional[str], expected: Optional[str]) -> bool:
    """Type-safe and timing-safe comparison preventing exceptions on non-ASCII input."""
    if not candidate or not expected:
        return False
    try:
        return secrets.compare_digest(str(candidate), str(expected))
    except Exception:
        return False
