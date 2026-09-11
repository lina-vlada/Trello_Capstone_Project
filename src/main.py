from fastapi import FastAPI, status, HTTPException
from database.database import SessionDep
import asyncio
from sqlalchemy import text

app = FastAPI()


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