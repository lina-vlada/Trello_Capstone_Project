from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from lib.database.postgres import SessionDep
from lib.database.redis import RedisDep
from entities.user import User
from modules.auth.service import _decode_access_token

bearer = HTTPBearer(auto_error=False)

async def get_current_user(
        creds: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer)],
        db: SessionDep,
        redis: RedisDep) -> User:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_access_token(creds.credentials)

    if await redis.exists(f"blacklist:access:{payload['jti']}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    result = await db.execute(select(User).where(User.id == payload["user_id"]))

    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not active",
        )

    return user

UserDep = Annotated[User,Depends(get_current_user)]