from sqlalchemy.orm import Session

from backend.core.enums import UserRole
from backend.core.security import hash_password
from backend.models.user import User


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, username: str, email: str, password: str, role: str = UserRole.SALE) -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_seed_user(db: Session, username: str, email: str, password: str, role: str) -> User:
    """Tạo tài khoản seed nếu chưa có, hoặc đưa tài khoản sẵn có về đúng trạng thái chuẩn.

    Idempotent để mỗi lần khởi động backend đều cho ra cùng một kết quả: máy nào
    clone repo về cũng đăng nhập được bằng cùng bộ tài khoản, kể cả khi ai đó đã
    lỡ đổi mật khẩu hoặc khoá tài khoản đó trên DB dùng chung.
    """
    user = get_user_by_username(db, username)
    if user is None:
        return create_user(db, username=username, email=email, password=password, role=role)

    user.email = email
    user.hashed_password = hash_password(password)
    user.role = role
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user