import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from configs.config import get_config
from src.database.user_repository import UserRepository

logger = logging.getLogger(__name__)
cfg = get_config()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT authentication scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# --------------- Password Policy ---------------

_PASSWORD_MIN_LEN = 8
_PASSWORD_POLICY = re.compile(
    r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$"
)


def validate_password_complexity(password: str) -> None:
    """
    Enforce password strength:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Raises HTTPException(400) on failure.
    """
    if len(password) < _PASSWORD_MIN_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {_PASSWORD_MIN_LEN} characters long.",
        )
    if not _PASSWORD_POLICY.match(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one digit, and one special character."
            ),
        )


# --------------- Password Helpers ---------------


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of a password."""
    return pwd_context.hash(password)


# --------------- Token Helpers ---------------


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token with iat and jti claims."""
    to_encode = data.copy()
    now = datetime.now(tz=timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=cfg.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Standard claims: exp, iat, jti
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),  # unique token ID — enables future revocation
    })
    encoded_jwt = jwt.encode(to_encode, cfg.JWT_SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency to retrieve the current user from the HttpOnly cookie or Authorization header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Try fetching from cookie first, fallback to Authorization header
    token = request.cookies.get("access_token")
    if not token:
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            token,
            cfg.JWT_SECRET_KEY,
            algorithms=[cfg.JWT_ALGORITHM],  # list — pin algorithm, reject "none"
        )
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_repo = UserRepository()
    user = user_repo.get_user_by_email(email=email)
    if user is None:
        raise credentials_exception

    return user
