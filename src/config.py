import os 
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings

def read_secrets(name: str, default_path: str | None = None) -> str | None:
    path = os.getenv(f"{name}_FILE", default_path)
    if path and Path(path).is_file():
        return Path(path).read_text().strip()
    return os.getenv(name)

class AuthJWT(BaseModel):
    algorithm: str = "RS256"
    access_token_expire_minute: int = 15
    refresh_token_expire_days: int = 7

    @property
    def private_key(self) -> str:
        key = read_secrets("PRIVATE_KEY", default_path="certs/private.pem")
        if not key:
            raise FileNotFoundError("The key is not found")
        return key

    @property
    def public_key(self) -> str:
        key = read_secrets("PUBLIC_KEY", default_path="certs/public.pem")
        if not key:
            raise FileNotFoundError("The key is not found")
        return key

class Settings(BaseSettings):
    postgres_user: str
    postgres_db: str
    postgres_host: str = "db"
    redis_url: str = "redis://redis:6379/0"
    auth_jwt: AuthJWT = AuthJWT()

    @property
    def database_url(self) -> str:
        password = read_secrets("POSTGRES_PASSWORD")
        return f"postgresql+asyncpg://{self.postgres_user}:{password}@{self.postgres_host}:5432/{self.postgres_db}"

settings = Settings()