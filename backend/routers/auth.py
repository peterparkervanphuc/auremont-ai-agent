from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user
from backend.core.mysql_client import get_db
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from backend.models.user import User
from backend.repositories.user import get_user_by_username
from backend.schemas.user import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    """Đăng nhập nội bộ Sale/Admin — role trong token quyết định routing."""
    user = get_user_by_username(db, form.username)

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return TokenResponse(
        access_token=create_access_token(subject=user.username, role=user.role),
        refresh_token=create_refresh_token(subject=user.username),
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Đổi refresh token lấy access token mới.

    Access token chỉ sống vài chục phút; nếu không có endpoint này thì Sale đang
    tư vấn giữa chừng sẽ bị văng ra màn hình đăng nhập khi token hết hạn.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    claims = decode_token(payload.refresh_token)
    # Bắt buộc type == "refresh": không cho dùng access token để tự gia hạn vô hạn.
    if claims is None or claims.get("type") != "refresh":
        raise credentials_error

    username = claims.get("sub")
    if username is None:
        raise credentials_error

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_error

    return TokenResponse(
        access_token=create_access_token(subject=user.username, role=user.role),
        refresh_token=create_refresh_token(subject=user.username),
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)) -> None:
    """Đăng xuất.

    JWT là stateless nên token vẫn hợp lệ tới khi hết hạn — client phải xoá token
    khỏi máy. Endpoint này tồn tại để client có điểm gọi thống nhất và để ghi vết.
    TODO: thêm token denylist (Redis) nếu cần thu hồi tức thì.
    """
    return None
