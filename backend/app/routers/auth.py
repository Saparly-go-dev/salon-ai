from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.deps import CurrentUser, Db, api_error, rate_limiter
from app.models import Role, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Db, request: Request):
    rate_limiter.check(f"register:{request.client.host}", limit=20, window_seconds=3600)
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise api_error(409, "email_taken")
    # Роль всегда client: сотрудников создаёт только администратор
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        role=Role.client,
    )
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Db, request: Request):
    email = body.email.lower()
    rate_limiter.check(f"login:{request.client.host}:{email}", limit=10, window_seconds=300)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise api_error(401, "invalid_credentials")
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
