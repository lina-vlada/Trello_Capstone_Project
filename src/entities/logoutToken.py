from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class LogoutToken(Base):
    __tablename__ = "logout_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)