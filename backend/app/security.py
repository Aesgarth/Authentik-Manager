import os
import time
import hmac
import hashlib
import secrets
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("authentik_manager.security")

# --- Password Hashing (PBKDF2-HMAC-SHA256) ---

def hash_password(password: str) -> str:
    """Hashes a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt = secrets.token_bytes(16)
    iterations = 100_000
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
    "secret",
    "admin123",
    "",
}

def resolve_secret_key(configured_key: str, data_dir: str = "data") -> str:
    """
    Ensures a cryptographically secure SECRET_KEY is always used:
    1. If configured_key is provided and not a known default (and >= 32 chars), uses it.
    2. Otherwise, looks for a persistent key file in data_dir/.secret_key.
    3. If neither exists, generates a secure random 64-char key and writes it to data_dir/.secret_key.
    """
    clean_key = (configured_key or "").strip()
    if clean_key not in DEFAULT_INSECURE_KEYS and len(clean_key) >= 32:
        return clean_key

    key_file = os.path.join(data_dir, ".secret_key")
    try:
        if os.path.exists(key_file):
            with open(key_file, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if len(saved) >= 32:
                    return saved
    except Exception as e:
        logger.warning(f"Could not read persistent secret key file {key_file}: {e}")

    # Generate a new persistent key
    generated = secrets.token_hex(32)
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(generated)
        logger.info(f"Generated new secure persistent secret key in {key_file}")
    except Exception as e:
        logger.warning(f"Could not persist secret key to {key_file}: {e}")

    return generated

# --- In-Memory Rate Limiting for Login Attempts ---

_login_attempts: dict[str, list[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300 # 5 minutes

def is_login_rate_limited(client_ip: str) -> bool:
    """Checks if client_ip has exceeded max failed login attempts."""
    now = time.time()
    attempts = _login_attempts.get(client_ip, [])
    # Keep attempts within the active window
    active_attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[client_ip] = active_attempts
    return len(active_attempts) >= MAX_LOGIN_ATTEMPTS

def record_failed_login(client_ip: str) -> None:
    """Records a failed login attempt for client_ip."""
    now = time.time()
    if client_ip not in _login_attempts:
        _login_attempts[client_ip] = []
    _login_attempts[client_ip].append(now)

def reset_login_attempts(client_ip: str) -> None:
    """Clears failed login attempts for client_ip upon successful authentication."""
    _login_attempts.pop(client_ip, None)

# --- SSRF and URL Validation ---

DISALLOWED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
    "100.100.100.200",
}

def validate_external_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validates an external URL for SSRF hazards:
    - Must be http:// or https://
    - Must not target cloud metadata endpoints
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"

    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted."

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "URL must include a valid hostname"

        if hostname in DISALLOWED_HOSTS:
            return False, f"Target host '{hostname}' is not permitted."

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
