from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
import jwt
import pytest
from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from config import settings
from entities.refresh_token import RefreshToken
from modules.auth import service
from modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from modules.auth.service import (
    _create_access_token,
    _create_refresh_token,
    _decode_access_token,
    _decode_refresh_token,
    _hash_password,
    _token_hash,
    _verify_password,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)


def _query_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


def _integrity_error():
    return IntegrityError("INSERT", {}, Exception("duplicate"))


def _user(*, user_id=10, is_active=True, password_hash="hashed-password"):
    return SimpleNamespace(
        id=user_id,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        is_active=is_active,
        password_hash=password_hash,
    )


def test_hash_and_verify_password():
    password = "correct-horse-battery"
    hashed = _hash_password(password)

    assert hashed != password
    assert _verify_password(password, hashed)
    assert not _verify_password("wrong-password", hashed)


@pytest.mark.parametrize("invalid_hash",["not-a-hash", "", "$2b$12$short", "5f4dcc3b5aa765d61d8327deb882cf99"])
def test_verify_password_rejects_malformed_hash(invalid_hash):
    assert not _verify_password("password", invalid_hash)


def test_token_hash_is_sha256():
    assert _token_hash("example-token") == sha256(b"example-token").hexdigest()


def test_create_access_token_has_required_claims_and_unique_jti():
    first = _create_access_token(10, timedelta(minutes=15))
    second = _create_access_token(10, timedelta(minutes=15))
    payload = jwt.decode(
        first,
        settings.auth_jwt.public_key,
        algorithms=[settings.auth_jwt.algorithm],
    )

    assert payload["user_id"] == 10
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]
    assert payload["jti"]
    assert first != second


def test_create_refresh_token_returns_matching_expiration():
    token, expires_at = _create_refresh_token(10, timedelta(days=7))
    payload = jwt.decode(
        token,
        settings.auth_jwt.public_key,
        algorithms=[settings.auth_jwt.algorithm],
    )

    assert payload["user_id"] == 10
    assert payload["type"] == "refresh"
    assert payload["jti"]
    assert payload["exp"] == int(expires_at.timestamp())


def test_decode_refresh_token_returns_user_id():
    token, _ = _create_refresh_token(10, timedelta(days=7))

    assert _decode_refresh_token(token) == 10


@pytest.mark.parametrize("token_factory",[
        lambda: _create_access_token(10, timedelta(minutes=15)),
        lambda: _create_refresh_token(10, timedelta(minutes=-1))[0],
        lambda: "not.a.jwt",
    ],
)
def test_decode_refresh_token_rejects_wrong_type_expired_and_malformed(token_factory):
    with pytest.raises(HTTPException) as exc_info:
        _decode_refresh_token(token_factory())

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize("user_id", [None, {"invalid": "id"}, "not-an-integer"])
def test_decode_refresh_token_rejects_invalid_user_id(user_id):
    claims = {"type": "refresh"}
    if user_id is not None:
        claims["user_id"] = user_id
    token = jwt.encode(
        claims,
        settings.auth_jwt.private_key,
        algorithm=settings.auth_jwt.algorithm,
    )

    with pytest.raises(HTTPException) as exc_info:
        _decode_refresh_token(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_decode_access_token_returns_valid_claims():
    token = _create_access_token(10, timedelta(minutes=15))

    payload = _decode_access_token(token)

    assert payload["user_id"] == 10
    assert payload["type"] == "access"
    assert payload["jti"]


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda: _create_refresh_token(10, timedelta(days=7))[0],
        lambda: _create_access_token(10, timedelta(minutes=-1)),
        lambda: "not.a.jwt",
    ],
)
def test_decode_access_token_rejects_wrong_type_expired_and_malformed(token_factory):
    with pytest.raises(HTTPException) as exc_info:
        _decode_access_token(token_factory())

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_decode_access_token_requires_jti():
    token = jwt.encode(
        {
            "user_id": 10,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        settings.auth_jwt.private_key,
        algorithm=settings.auth_jwt.algorithm,
    )

    with pytest.raises(HTTPException) as exc_info:
        _decode_access_token(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_register_user_adds_commits_refreshes_and_returns_created_user(auth_db):
    db = auth_db

    async def set_user_id(user):
        user.id = 17

    db.refresh.side_effect = set_user_id
    data = RegisterRequest(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        password="secure-password",
    )

    result = await register_user(db, data)

    created_user = db.add.call_args.args[0]
    assert created_user.email == data.email
    assert _verify_password(data.password, created_user.password_hash)
    assert result == {"id": 17, "email": data.email}
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(created_user)


@pytest.mark.asyncio
async def test_register_user_rolls_back_and_returns_conflict_on_duplicate_email(auth_db):
    db = auth_db
    db.commit.side_effect = _integrity_error()
    data = RegisterRequest(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        password="secure-password",
    )

    with pytest.raises(HTTPException) as exc_info:
        await register_user(db, data)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "An account with this email already exists"
    db.rollback.assert_awaited_once()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_user_issues_tokens_and_persists_hashed_refresh_token(auth_db):
    db = auth_db
    db.execute.return_value = _query_result(_user())
    data = LoginRequest(email="ada@example.com", password="secure-password")

    with patch.object(service, "_verify_password", return_value=True):
        response = await login_user(db, data)

    assert isinstance(response, TokenResponse)
    access_payload = _decode_access_token(response.access_token)
    refresh_user_id = _decode_refresh_token(response.refresh_token)
    stored_refresh_token = db.add.call_args.args[0]
    assert access_payload["user_id"] == 10
    assert refresh_user_id == 10
    assert isinstance(stored_refresh_token, RefreshToken)
    assert stored_refresh_token.user_id == 10
    assert stored_refresh_token.token_hash == _token_hash(response.refresh_token)
    assert stored_refresh_token.expires_at > datetime.now(timezone.utc)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    "user, password_matches",
    [
        (None, True),
        (_user(is_active=False), True),
        (_user(), False),
    ],
)
@pytest.mark.asyncio
async def test_login_user_rejects_unknown_inactive_or_wrong_password(user, password_matches, auth_db):
    db = auth_db
    db.execute.return_value = _query_result(user)
    data = LoginRequest(email="ada@example.com", password="wrong-or-right")

    with patch.object(service, "_verify_password", return_value=password_matches):
        with pytest.raises(HTTPException) as exc_info:
            await login_user(db, data)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_user_rolls_back_on_refresh_token_insert_conflict(auth_db):
    db = auth_db
    db.execute.return_value = _query_result(_user())
    db.commit.side_effect = _integrity_error()
    data = LoginRequest(email="ada@example.com", password="secure-password")

    with patch.object(service, "_verify_password", return_value=True):
        with pytest.raises(HTTPException) as exc_info:
            await login_user(db, data)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Failed to register session"
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_access_token_requires_stored_token_and_active_user(auth_db):
    token, _ = _create_refresh_token(10, timedelta(days=7))
    user = _user()
    db = auth_db
    db.execute.side_effect = [_query_result(SimpleNamespace()), _query_result(user)]

    response = await refresh_access_token(db, token)

    assert response.refresh_token == token
    access_payload = _decode_access_token(response.access_token)
    assert access_payload["user_id"] == user.id
    assert response.token_type == "bearer"
    db.execute.assert_awaited()
    assert db.execute.await_count == 2
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_access_token_rejects_token_missing_from_database(auth_db):
    token, _ = _create_refresh_token(10, timedelta(days=7))
    db = auth_db
    db.execute.return_value = _query_result(None)

    with pytest.raises(HTTPException) as exc_info:
        await refresh_access_token(db, token)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    db.execute.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("user", [None, _user(is_active=False)])
@pytest.mark.asyncio
async def test_refresh_access_token_rejects_missing_or_inactive_user(user, auth_db):
    token, _ = _create_refresh_token(10, timedelta(days=7))
    db = auth_db
    db.execute.side_effect = [_query_result(SimpleNamespace()), _query_result(user)]

    with pytest.raises(HTTPException) as exc_info:
        await refresh_access_token(db, token)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert db.execute.await_count == 2
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_access_token_rejects_invalid_jwt_before_database_access(auth_db):
    db = auth_db

    with pytest.raises(HTTPException) as exc_info:
        await refresh_access_token(db, "not.a.jwt")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_deletes_refresh_token_and_blacklists_access_token(auth_db, auth_redis):
    refresh_token, _ = _create_refresh_token(10, timedelta(days=7))
    access_token = _create_access_token(10, timedelta(minutes=15))
    db = auth_db
    redis = auth_redis
    db.execute.return_value = SimpleNamespace(rowcount=1)

    await logout_user(db, redis, refresh_token, access_token)

    delete_statement = db.execute.await_args.args[0]
    assert "refresh_tokens" in str(delete_statement)
    redis.set.assert_awaited_once()
    key, value = redis.set.await_args.args
    ttl = redis.set.await_args.kwargs["ex"]
    assert key.startswith("blacklist:access:")
    assert value == "1"
    assert 0 < ttl <= 15 * 60
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_without_access_token_skips_redis_blacklist(auth_db, auth_redis):
    refresh_token, _ = _create_refresh_token(10, timedelta(days=7))
    db = auth_db
    redis = auth_redis
    db.execute.return_value = SimpleNamespace(rowcount=1)

    await logout_user(db, redis, refresh_token)

    redis.set.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_rejects_refresh_token_missing_from_database(auth_db, auth_redis):
    refresh_token, _ = _create_refresh_token(10, timedelta(days=7))
    db = auth_db
    redis = auth_redis
    db.execute.return_value = SimpleNamespace(rowcount=0)

    with pytest.raises(HTTPException) as exc_info:
        await logout_user(db, redis, refresh_token)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_rejects_invalid_access_token_before_database_access(auth_db, auth_redis):
    refresh_token, _ = _create_refresh_token(10, timedelta(days=7))
    db = auth_db
    redis = auth_redis

    with pytest.raises(HTTPException) as exc_info:
        await logout_user(db, redis, refresh_token, "not.a.jwt")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    db.execute.assert_not_awaited()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_returns_unavailable_and_rolls_back_when_redis_fails(auth_db, auth_redis):
    refresh_token, _ = _create_refresh_token(10, timedelta(days=7))
    access_token = _create_access_token(10, timedelta(minutes=15))
    db = auth_db
    redis = auth_redis
    db.execute.return_value = SimpleNamespace(rowcount=1)
    redis.set.side_effect = RedisError("Redis unavailable")

    with pytest.raises(HTTPException) as exc_info:
        await logout_user(db, redis, refresh_token, access_token)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
