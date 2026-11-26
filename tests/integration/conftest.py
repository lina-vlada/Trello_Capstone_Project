import os
from urllib.parse import urlsplit
from typing import Any, get_args
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from lib.database.postgres import Base, get_db
from lib.database.redis import RedisDep
from main import app


class APIClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def post(self,path: str,*,json_body: Any = None,headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.post(path, json=json_body, headers=headers)

    async def patch(self,path: str,*,json_body: Any = None,headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.patch(path, json=json_body, headers=headers)

    async def get(self, path: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.get(path, headers=headers)

    async def delete(self, path: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.delete(path, headers=headers)


@pytest_asyncio.fixture
async def integration_engine():
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://integration:integration@127.0.0.1:55439/trello_test",
    )

    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must point to a dedicated PostgreSQL test database")
    if "test" not in (parsed_url.database or "").lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'")

    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def integration_db(integration_engine):
    async with integration_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with session_factory() as session:
            yield session
        await transaction.rollback()


@pytest_asyncio.fixture
async def integration_redis():
    redis_url = os.getenv(
        "TEST_REDIS_URL",
        "redis://127.0.0.1:16389/1",
    )

    parsed_url = urlsplit(redis_url)
    try:
        database_number = int(parsed_url.path.lstrip("/") or "0")
    except ValueError:
        pytest.fail("TEST_REDIS_URL must use a numeric Redis database index")
    if database_number == 0:
        pytest.fail("TEST_REDIS_URL must use a non-default Redis database (index 1 or higher)")

    redis = Redis.from_url(redis_url, decode_responses=True)
    await redis.ping()
    yield redis
    await redis.aclose()


@pytest_asyncio.fixture
async def api(integration_db, integration_redis):
    async def override_db():
        yield integration_db

    async def override_redis():
        return integration_redis

    redis_dependency = get_args(RedisDep)[1].dependency
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[redis_dependency] = override_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield APIClient(client)
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def redis_keys(integration_redis):
    keys: set[str] = set()

    def track(key: str) -> None:
        keys.add(key)

    yield track

    if keys:
        await integration_redis.delete(*keys)
