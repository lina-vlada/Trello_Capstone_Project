from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
import bcrypt
from config import settings
from database.database import RedisDep, SessionDep
from entities.refreshToken import RefreshToken
from entities.user import User
from fastapi import HTTPException, status
import jwt
from modules.auth.authSchema import LoginRequest, RegisterRequest, TokenResponse
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _create_access_token(user_id: int, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": "access",
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.auth_jwt.private_key, algorithm=settings.auth_jwt.algorithm)


def _create_refresh_token(user_id: int, lifetime: timedelta) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + lifetime
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "iat": now,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    encoded = jwt.encode(payload, settings.auth_jwt.private_key, algorithm=settings.auth_jwt.algorithm)
    return encoded, expires_at


def _decode_refresh_token(refresh_token: str) -> int:
    try:
        payload = jwt.decode(
            refresh_token,
            settings.auth_jwt.public_key,
            algorithms=[settings.auth_jwt.algorithm],
        )
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError("Wrong token type")

        return int(payload["user_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc


def _decode_access_token(access_token: str) -> dict:
    try:
        payload = jwt.decode(
            access_token,
            settings.auth_jwt.public_key,
            algorithms=[settings.auth_jwt.algorithm],
            options={"require": ["exp", "jti", "user_id", "type"]},
        )
        if payload.get("type") != "access" or not isinstance(payload.get("jti"), str):
            raise jwt.InvalidTokenError("Invalid access token format")
        return payload
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc


async def register_user(db: SessionDep, data: RegisterRequest) -> dict:
    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        password_hash=_hash_password(data.password),
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

    access_token = _create_access_token(
        user_id=user.id,
        lifetime=timedelta(minutes=settings.auth_jwt.access_token_expire_minute),
    )
    refresh_token, refresh_exp = _create_refresh_token(
        user_id=user.id,
        lifetime=timedelta(days=settings.auth_jwt.refresh_token_expire_days),
    )

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_token_hash(refresh_token),
            expires_at=refresh_exp,
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to register session",
        ) from exc

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


async def refresh_access_token(db: SessionDep, refresh_token: str) -> TokenResponse:
    user_id = _decode_refresh_token(refresh_token)
    token_hash = _token_hash(refresh_token)
    now = datetime.now(timezone.utc)

    token_result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.token_hash == token_hash,
            RefreshToken.expires_at > now,
        )
    )
    stored_token = token_result.scalar_one_or_none()
    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    new_access_token = _create_access_token(
        user_id=user.id,
        lifetime=timedelta(minutes=settings.auth_jwt.access_token_expire_minute),
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


async def logout_user(
    db: SessionDep,
    redis: RedisDep,
    refresh_token: str,
    access_token: str | None = None,
) -> None:
    user_id = _decode_refresh_token(refresh_token)

    access_payload = _decode_access_token(access_token) if access_token else None

    result = await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.token_hash == _token_hash(refresh_token),
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if access_payload is not None:
        remaining_ttl = int(access_payload["exp"] - datetime.now(timezone.utc).timestamp())
        if remaining_ttl > 0:
            try:
                await redis.set(
                    f"blacklist:access:{access_payload['jti']}",
                    "1",
                    ex=remaining_ttl,
                )
            except RedisError as exc:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication cache service unavailable",
                ) from exc

    await db.commit()