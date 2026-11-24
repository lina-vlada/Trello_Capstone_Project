from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import status
from modules.auth.service import _create_refresh_token, _decode_access_token
from tests.integration.factories import login_user, register_user


@pytest.mark.asyncio
async def test_register_login_and_current_user_access(api):
    user = await register_user(api)
    tokens = await login_user(api, user)

    boards = await api.get("/boards/", headers=tokens["headers"])

    assert boards.status_code == status.HTTP_200_OK
    assert boards.json() == []


@pytest.mark.asyncio
async def test_register_normalizes_email_and_rejects_duplicate(api):
    email = f" Person-{uuid4().hex}@Example.COM "
    registration = await api.post(
        "/auth/register",
        json_body={
            "first_name": "Test",
            "last_name": "User",
            "email": email,
            "password": "integration-password",
        },
    )
    duplicate = await api.post(
        "/auth/register",
        json_body={
            "first_name": "Test",
            "last_name": "User",
            "email": email.strip().lower(),
            "password": "integration-password",
        },
    )

    assert registration.status_code == status.HTTP_201_CREATED
    assert registration.json()["email"] == email.strip().lower()
    assert duplicate.status_code == status.HTTP_409_CONFLICT


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "Test", "last_name": "User", "email": "x@example.com", "password": "short"},
        {"first_name": "Test", "last_name": "User", "email": "x@example.com"},
    ],
)
@pytest.mark.asyncio
async def test_register_rejects_invalid_payload(api, payload):
    response = await api.post("/auth/register", json_body=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_login_rejects_unknown_user_and_wrong_password(api):
    unknown = await api.post(
        "/auth/login",
        json_body={"email": f"unknown-{uuid4().hex}@example.com", "password": "wrong-password"},
    )
    user = await register_user(api)
    wrong_password = await api.post(
        "/auth/login",
        json_body={"email": user["email"], "password": "wrong-password"},
    )

    assert unknown.status_code == status.HTTP_401_UNAUTHORIZED
    assert wrong_password.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_refresh_rotates_access_token_and_rejects_unstored_or_invalid_tokens(api):
    user = await register_user(api)
    tokens = await login_user(api, user)
    refreshed = await api.post(
        "/auth/refresh",
        json_body={"refresh_token": tokens["refresh_token"]},
    )
    unpersisted_token, _ = _create_refresh_token(-1, timedelta(days=1))
    missing = await api.post(
        "/auth/refresh", json_body={"refresh_token": unpersisted_token}
    )
    invalid = await api.post("/auth/refresh", json_body={"refresh_token": "not.a.jwt"})

    assert refreshed.status_code == status.HTTP_200_OK
    assert refreshed.json()["refresh_token"] == tokens["refresh_token"]
    assert refreshed.json()["access_token"] != tokens["access_token"]
    assert missing.status_code == status.HTTP_403_FORBIDDEN
    assert invalid.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_logout_blacklists_access_token_and_invalidates_refresh_token(api, integration_redis, redis_keys):
    user = await register_user(api)
    tokens = await login_user(api, user)
    logout = await api.post(
        "/auth/logout",
        json_body={"refresh_token": tokens["refresh_token"]},
        headers=tokens["headers"],
    )
    access_payload = _decode_access_token(tokens["access_token"])
    blacklist_key = f"blacklist:access:{access_payload['jti']}"
    redis_keys(blacklist_key)
    refresh_after_logout = await api.post(
        "/auth/refresh",
        json_body={"refresh_token": tokens["refresh_token"]},
    )
    access_after_logout = await api.get("/boards/", headers=tokens["headers"])

    assert logout.status_code == status.HTTP_204_NO_CONTENT
    assert await integration_redis.exists(blacklist_key) == 1
    assert refresh_after_logout.status_code == status.HTTP_403_FORBIDDEN
    assert access_after_logout.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_protected_routes_reject_missing_and_malformed_credentials(api):
    missing = await api.get("/boards/")
    malformed = await api.get("/boards/", headers={"Authorization": "Bearer not.a.jwt"})

    assert missing.status_code == status.HTTP_401_UNAUTHORIZED
    assert malformed.status_code == status.HTTP_401_UNAUTHORIZED
