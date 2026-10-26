from fastapi import Depends
from config import settings
from typing import Annotated 
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import redis.asyncio as aioredis

DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL)
new_session = async_sessionmaker(engine, expire_on_commit=False)
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


def create_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    return redis_client

class Base(DeclarativeBase):
    pass

async def get_db():
    async with new_session() as session:
        yield session

SessionDep = Annotated[AsyncSession,Depends(get_db)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]