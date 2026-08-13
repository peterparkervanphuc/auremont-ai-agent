import logging
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from backend.core.config import settings

logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": subject, "role": role, "type": "access", "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": subject, "type": "refresh", "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        # The exception type separates an ordinary expiry (ExpiredSignatureError)
        # from a tampered or wrongly-signed token — indistinguishable before, since
        # both surfaced as the same generic 401.
        # The token itself is never logged, not even a prefix: a JWT prefix is a
        # decodable header plus the start of the payload.
        logger.warning(
            "JWT rejected",
            extra={"event": "auth.token.rejected", "reason": type(exc).__name__, "detail": str(exc)[:120]},
        )
        return None
