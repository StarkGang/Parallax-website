"""Token generation, hashing, encryption and constant-time comparison."""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def _keys() -> list[bytes]:
    settings = get_settings()
    keys = [settings.server_secret_key.encode()]
    if settings.server_secret_key_previous:
        keys.append(settings.server_secret_key_previous.encode())
    return keys


def hmac_sha256(key: bytes, message: str) -> str:
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    return hmac_sha256(_keys()[0], token)


def token_matches_hash(token: str, expected_hash: str) -> bool:
    for key in _keys():
        if hmac.compare_digest(hmac_sha256(key, token), expected_hash):
            return True
    return False


def derive_csrf_token(csrf_secret: str, session_id: str) -> str:
    return hmac_sha256(csrf_secret.encode(), session_id)


def constant_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _fernet(material: str) -> Fernet:
    digest = hashlib.sha256(f"parallax-pii:{material}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _pii_fernet() -> Fernet:
    return _fernet(get_settings().server_secret_key)


def encrypt_pii(value: str) -> str:
    return _pii_fernet().encrypt(value.encode()).decode()


def decrypt_pii(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _pii_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def encrypt_secret(value: str, *, domain: str = "totp") -> str:
    settings = get_settings()
    material = settings.totp_encryption_key or settings.server_secret_key
    key_material = f"{domain}:{material}".replace(":", "|")
    return _fernet(key_material).encrypt(value.encode()).decode()


def decrypt_secret(value: str, *, domain: str = "totp") -> str | None:
    settings = get_settings()
    material = settings.totp_encryption_key or settings.server_secret_key
    key_material = f"{domain}:{material}".replace(":", "|")
    try:
        return _fernet(key_material).decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def hash_pii(value: str) -> str:
    return hmac_sha256(_keys()[0], value.strip().lower())


def recovery_code() -> str:
    raw = secrets.token_hex(5).upper()
    return f"{raw[:5]}-{raw[5:]}"


def short_reference(prefix: str = "PX") -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"

