import hashlib
import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

PASSWORD_HASHER = PasswordHasher(type=Type.ID)
# One fixed valid dummy hash makes unknown-user login perform the same expensive verify.
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    # SQLite test adapter returns naive timestamps; production uses timestamptz.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False
