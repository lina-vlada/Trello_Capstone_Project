from fastapi import FastAPI, status, HTTPException
from redis_fastapi import FastAPIRedis
from lib.database.redis import RedisDep, setup_redis, ping_redis
from lib.database.postgres import SessionDep
from modules.auth.router import router as auth_router
from modules.boards.router import router as boards_router
import asyncio
from sqlalchemy import text

app = FastAPI()
setup_redis(app)

app.include_router(auth_router)
app.include_router(boards_router)


@app.get("/healthz",include_in_schema=False)
async def health_check():
    return {"status":"ok"}

@app.get("/readyz",include_in_schema=False)
async def ready_check(db: SessionDep, redis: RedisDep):
    try:
        await asyncio.wait_for(
            db.execute(text("SELECT 1")),
            timeout=5.0
        )
        await asyncio.wait_for(
            ping_redis(redis),
            timeout=5.0
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)