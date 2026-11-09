"""Password hashing (Argon2id), JWT helpers and secret encryption."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.core.errors import NotAuthenticated
from app.core.ids import new_public_id

TokenType = Literal["tenant", "platform", "family"]

_hasher = PasswordHasher()  # argon2id with library defaults (OWASP compliant)


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# ---------------------------------------------------------------- tokens
def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    *,
    subject: str,
    token_type: TokenType,
    tenant_id: str | None = None,
    session_id: str | None = None,
    ttl_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes or settings.access_token_ttl_minutes),
        "jti": new_public_id(),
    }
    if tenant_id is not None:
        payload["tid"] = tenant_id
    if session_id is not None:
        payload["sid"] = session_id
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise NotAuthenticated("Access token expired", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise NotAuthenticated("Invalid access token", code="INVALID_TOKEN") from exc


# ---------------------------------------------------------------- secret encryption
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.secret_encryption_key is not None:
        key = settings.secret_encryption_key.get_secret_value().encode()
    else:  # development fallback: derive a key from the secret key
        digest = hashlib.sha256(settings.secret_key.get_secret_value().encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt_secret(value: bytes) -> str:
    return _fernet().decrypt(value).decode()
