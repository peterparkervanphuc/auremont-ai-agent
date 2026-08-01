from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.core.mysql_client import get_db
from backend.core.security import create_access_token, create_refresh_token, verify_password
from backend.repositories.user import get_user_by_username
from backend.schemas.user import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    """Đăng nhập nội bộ Sale/Admin — role trong token quyết định routing (CLAUDE.md §6.2)."""
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
