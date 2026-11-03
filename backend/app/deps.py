import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Role, User
from app.security import decode_token

Db = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


def api_error(status: int, code: str) -> HTTPException:
    # Интерфейс переводит ошибку на язык пользователя по коду
    return HTTPException(status_code=status, detail={"code": code})


def get_current_user(db: Db, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    user_id = decode_token(credentials.credentials) if credentials else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise api_error(401, "not_authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise api_error(403, "forbidden")
        return user

    return check


AdminUser = Annotated[User, Depends(require_roles(Role.admin))]
StaffUser = Annotated[User, Depends(require_roles(Role.admin, Role.master))]


class RateLimiter:
    """Счётчик запросов в памяти процесса: защищает вход и расходы на API модели."""

    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise api_error(429, "rate_limited")
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = RateLimiter()
