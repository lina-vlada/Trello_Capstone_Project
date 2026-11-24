from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from modules.auth import dependencies, router as auth_router
from modules.auth.schemas import LoginRequest, RefreshTokenRequest, RegisterRequest, TokenResponse


def _user(*, is_active=True):
    return SimpleNamespace(id=10, is_active=is_active)


@pytest.mark.asyncio
async def test_register_route_forwards_validated_data_and_returns_created_user(auth_dependencies):
    db, _, _ = auth_dependencies
    data = RegisterRequest(
        first_name="Ada",
        last_name="Lovelace",
        email=" ADA@EXAMPLE.COM ",
        password="correct-horse",
    )
    result = {"id": 17, "email": "ada@example.com"}

    with patch.object(auth_router, "register_user", new_callable=AsyncMock, return_value=result) as register:
        response = await auth_router.register(data, db)

    assert response == result
    register.assert_awaited_once_with(db, data)
    assert data.email == "ada@example.com"


@pytest.mark.asyncio
async def test_register_schema_rejects_password_below_minimum_length():
    with pytest.raises(ValueError):
        RegisterRequest(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            password="short",
        )


@pytest.mark.asyncio
async def test_login_route_forwards_normalized_data_and_returns_tokens(auth_dependencies):
    db, _, _ = auth_dependencies
    data = LoginRequest(email=" ADA@EXAMPLE.COM ", password="password")
    response = TokenResponse(
        access_token="access-token",
        refresh_token="refresh-token",
        token_type="bearer",
    )

    with patch.object(auth_router, "login_user", new_callable=AsyncMock, return_value=response) as login:
        result = await auth_router.login(data, db)

    assert result is response
    assert data.email == "ada@example.com"
    login.assert_awaited_once_with(db, data)


@pytest.mark.asyncio
async def test_refresh_route_passes_refresh_token_and_returns_tokens(auth_dependencies):
    db, _, _ = auth_dependencies
    data = RefreshTokenRequest(refresh_token="refresh-token")
    response = TokenResponse(
        access_token="new-access-token",
        refresh_token="refresh-token",
        token_type="bearer",
    )

    with patch.object(
        auth_router,
        "refresh_access_token",
        new_callable=AsyncMock,
        return_value=response,
    ) as refresh:
        result = await auth_router.refresh(data, db)

    assert result is response
    refresh.assert_awaited_once_with(db, "refresh-token")


@pytest.mark.asyncio
async def test_logout_route_forwards_access_credentials(auth_dependencies):
    db, redis, user = auth_dependencies
    data = RefreshTokenRequest(refresh_token="refresh-token")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")

    with patch.object(auth_router, "logout_user", new_callable=AsyncMock) as logout:
        await auth_router.logout(data, db, redis, user, credentials)

    logout.assert_awaited_once_with(db, redis, "refresh-token", "access-token")


@pytest.mark.asyncio
async def test_current_user_rejects_missing_bearer_credentials(auth_db, auth_redis):
    db = auth_db
    redis = auth_redis

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_user(None, db, redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
    db.execute.assert_not_awaited()
    redis.exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_user_rejects_blacklisted_access_token(auth_db, auth_redis):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")
    db = auth_db
    redis = auth_redis
    redis.exists.return_value = 1

    with patch.object(
        dependencies,
        "_decode_access_token",
        return_value={"jti": "token-id", "user_id": 10},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await dependencies.get_current_user(credentials, db, redis)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Token has been revoked"
    redis.exists.assert_awaited_once_with("blacklist:access:token-id")
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("user", [None, _user(is_active=False)])
@pytest.mark.asyncio
async def test_current_user_rejects_missing_or_inactive_user(user, auth_db, auth_redis):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")
    db = auth_db
    redis = auth_redis
    redis.exists.return_value = 0
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: user)

    with patch.object(
        dependencies,
        "_decode_access_token",
        return_value={"jti": "token-id", "user_id": 10},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await dependencies.get_current_user(credentials, db, redis)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "User is not active"
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_current_user_returns_active_user(auth_db, auth_redis):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")
    user = _user()
    db = auth_db
    redis = auth_redis
    redis.exists.return_value = 0
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: user)

    with patch.object(
        dependencies,
        "_decode_access_token",
        return_value={"jti": "token-id", "user_id": 10},
    ):
        result = await dependencies.get_current_user(credentials, db, redis)

    assert result is user
    redis.exists.assert_awaited_once_with("blacklist:access:token-id")
    db.execute.assert_awaited_once()
