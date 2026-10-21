import jwt
import bcrypt
from hashlib import sha256
from database.database import SessionDep
from datetime import timedelta, datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from config import settings
from entities.logoutToken import LogoutToken
from entities.user import User
from modules.auth.authSchema import LoginRequest, RegisterRequest, TokenResponse


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False

def _create_access_token(user_id: int, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.auth_jwt.private_key, algorithm=settings.auth_jwt.algorithm)

def _create_refresh_token(user_id: int, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.auth_jwt.private_key, algorithm=settings.auth_jwt.algorithm)


def _decode_refresh_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.auth_jwt.public_key, algorithms=settings.auth_jwt.algorithm)
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError("Wrong token type")

        return int(payload["user_id"])

    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token!",
        ) from exc

def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


async def register_user(db: SessionDep, data: RegisterRequest):
    user = User(
        first_name = data.first_name,
        last_name = data.last_name,
        email = data.email,
        password_hash = _hash_password(data.password)
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    await db.refresh(user)
    
    return {"id": user.id, "email": user.email}

async def login_user(db: SessionDep, data: LoginRequest) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not _verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=_create_access_token(
            user.id,
            "access",
            timedelta(minutes=settings.auth_jwt.access_token_expire_minute),
        ),
        refresh_token=_create_refresh_token(
            user.id,
            "refresh",
            timedelta(days=settings.auth_jwt.refresh_token_expire_days),
        ),
        token_type="bearer",
    )
    
async def refresh_access_token(db: SessionDep, token: str) -> TokenResponse:
    user_id = _decode_refresh_token(token)

    revoked_result = await db.execute(
        select(LogoutToken).where(LogoutToken.token_hash == _token_hash(token))
    )
    if revoked_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    response = TokenResponse(
        access_token=_create_access_token(
            user.id,
            "access",
            timedelta(minutes=settings.auth_jwt.access_token_expire_minute),
        ),
        refresh_token=_create_refresh_token(
            user.id,
            "refresh",
            timedelta(days=settings.auth_jwt.refresh_token_expire_days),
        ),
        token_type="bearer",
    )
    await db.commit()
    return response



async def logout_user(db: SessionDep, token: str) -> None:
    _decode_refresh_token(token)
    await db.execute(
        insert(LogoutToken)
        .values(token_hash=_token_hash(token))
    )
    await db.commit()
