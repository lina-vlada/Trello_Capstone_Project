from fastapi import FastAPI, status, HTTPException
from database.database import SessionDep, create_redis_client
from modules.auth.controller import router as auth_router
import asyncio
from sqlalchemy import text

app = FastAPI()
app.include_router(auth_router)

async def startup() -> None:
    redis_client = create_redis_client()
    try:
        await redis_client.ping()
    except Exception:
        await redis_client.aclose()
        raise
    app.state.redis = redis_client

async def shutdown() -> None:
    await app.state.redis.aclose()

app.add_event_handler("startup", startup)
app.add_event_handler("shutdown", shutdown)


@app.get("/healthz",include_in_schema=False)
async def health_check():
    return {"status":"ok"}

@app.get("/readyz",include_in_schema=False)
async def ready_check(db: SessionDep):
    try:
        await asyncio.wait_for(
            db.execute(text("SELECT 1")),
            timeout=5.0
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)