import os

from fastapi import FastAPI
from redis_fastapi import FastAPIRedis, AsyncRedisDep
from config import settings


RedisDep = AsyncRedisDep

def setup_redis(app: FastAPI):
    os.environ["REDIS_URL"] = settings.redis_url
    FastAPIRedis(app).lifespan()

async def ping_redis(redis: RedisDep):
    try:
        return await redis.ping()
    except Exception:
        return False