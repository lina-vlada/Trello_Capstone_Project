from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def auth_db():
    db = AsyncMock()
    db.add = Mock()
    return db


@pytest.fixture
def auth_redis():
    return AsyncMock()


@pytest.fixture
def auth_dependencies(auth_db, auth_redis):
    user = SimpleNamespace(id=10, is_active=True)
    return auth_db, auth_redis, user


@pytest.fixture
def boards_db():
    db = AsyncMock()
    db.add = Mock()
    return db


@pytest.fixture
def boards_redis():
    return AsyncMock()


@pytest.fixture
def boards_user():
    return SimpleNamespace(id=1, email="member@example.com")


@pytest.fixture
def sections_db():
    db = AsyncMock()
    db.add = Mock()
    return db


@pytest.fixture
def sections_user():
    return SimpleNamespace(id=1)


@pytest.fixture
def tickets_db():
    db = AsyncMock()
    db.add = Mock()
    return db


@pytest.fixture
def tickets_user():
    return SimpleNamespace(id=1)
