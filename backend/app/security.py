from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: int) -> str:
    expires = datetime.now(UTC) + timedelta(hours=settings.jwt_ttl_hours)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
