from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.core.security import decode_token
from backend.models.user import User
from backend.repositories.user import get_user_by_username

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_error

    username = payload.get("sub")
    if username is None:
        raise credentials_error

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_error

    return user


def require_role(*roles: UserRole):
    """Cho phép user thuộc một trong các role truyền vào.

    Gọi với 1 role để khoá chặt (vd. require_role(UserRole.ADMIN)), hoặc nhiều
    role khi cả hai bên cùng dùng chung một luồng (vd. Chat mở cho SALE + ADMIN).
    """
    allowed = set(roles)

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _dependency
