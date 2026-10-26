from fastapi import APIRouter, status
from database.database import RedisDep, SessionDep
from modules.auth.authSchema import LoginRequest,RefreshTokenRequest,RegisterRequest,TokenResponse
from modules.auth.service import login_user,logout_user,refresh_access_token,register_user


router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: SessionDep):
    return await register_user(db, data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: SessionDep):
    return await login_user(db, data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, db: SessionDep):
    return await refresh_access_token(db, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshTokenRequest,
    db: SessionDep,
    redis: RedisDep,
) -> None:
    await logout_user(db, redis, data.refresh_token, data.access_token)