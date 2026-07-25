from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

# TODO: Implement JWT authentication endpoints
#
# POST /auth/register
#   - Accept: UserCreate schema (username, email, password, role)
#   - Hash password with passlib/bcrypt before saving
#   - Persist user via repositories/user.py → create_user()
#   - Return: UserResponse (no password)
#
# POST /auth/login
#   - Accept: OAuth2PasswordRequestForm (username, password)
#   - Verify password hash with passlib
#   - On success: generate access_token + refresh_token (JWT via python-jose)
#   - Return: {"access_token": ..., "refresh_token": ..., "token_type": "bearer"}
#
# POST /auth/refresh
#   - Accept: refresh_token in request body
#   - Validate and decode JWT, check expiry
#   - Return: new access_token
#
# Dependencies to create:
#   - get_current_user(token: str) → decodes JWT, returns User from DB
#   - require_role(role: str) → wraps get_current_user, raises 403 if role mismatch
