"""
Security utilities module.

Handles JWT token creation/verification and password hashing/verification
using industry-standard libraries (python-jose, passlib/bcrypt).
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing context (bcrypt)
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        plain_password: The raw password string to hash.

    Returns:
        str: The bcrypt-hashed password string.
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash.

    Args:
        plain_password: The raw password provided by the user.
        hashed_password: The stored bcrypt hash to compare against.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(subject: str, extra_claims: dict | None = None) -> str:
    """Create a short-lived JWT access token.

    Args:
        subject: The unique identifier to encode (typically user ID as string).
        extra_claims: Optional additional claims to include in the payload
            (e.g., {"role": "therapist"}).

    Returns:
        str: A signed JWT access token string.
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived JWT refresh token.

    Args:
        subject: The unique identifier to encode (typically user ID as string).

    Returns:
        str: A signed JWT refresh token string.
    """
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        dict: The decoded token payload.

    Raises:
        JWTError: If the token is invalid, expired, or has a bad signature.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def get_token_subject(token: str) -> str | None:
    """Safely extract the 'sub' claim from a JWT without raising exceptions.

    Args:
        token: The JWT string to inspect.

    Returns:
        str | None: The subject string, or None if decoding fails.
    """
    try:
        payload = decode_token(token)
        return payload.get("sub")
    except JWTError:
        return None
