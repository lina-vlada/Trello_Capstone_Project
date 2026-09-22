import os 
from pathlib import Path
from pydantic_settings import BaseSettings

def read_secrets(name: str) -> str | None:
    path = os.getenv(f"{name}_FILE")
    if path and Path(path).is_file():
        return Path(path).read_text().strip()
    return os.getenv(name)


class Settings(BaseSettings):
    postgres_user: str
    postgres_db: str
    postgres_host: str = "db"

    @property
    def database_url(self) -> str:
        password = read_secrets("POSTGRES_PASSWORD")
        return f"postgresql+asyncpg://{self.postgres_user}:{password}@{self.postgres_host}:5432/{self.postgres_db}"

settings = Settings()