from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["Users"])

# TODO: Implement user management endpoints (requires auth middleware first)
#
# GET /users/me
#   - Dependency: get_current_user (from auth)
#   - Return: UserResponse of the authenticated user
#
# GET /users/{user_id}
#   - Dependency: require_role("admin")
#   - Fetch user by ID from DB
#   - Raise 404 if not found
#   - Return: UserResponse
#
# PATCH /users/{user_id}
#   - Dependency: require_role("admin")
#   - Accept partial update: role, is_active
#   - Persist via repositories/user.py → update_user()
#   - Return: updated UserResponse
#
# DELETE /users/{user_id}
#   - Dependency: require_role("admin")
#   - Soft-delete: set is_active=False (do not hard-delete)
#   - Return: 204 No Content
