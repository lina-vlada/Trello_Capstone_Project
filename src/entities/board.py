from sqlalchemy import String, Boolean
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.boardUser import BoardUser
    from entities.section import Section

class Board(Base):
    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100),nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    memberships: Mapped[list["BoardUser"]] = relationship(back_populates="board", cascade="all, delete-orphan", passive_deletes=True)

    sections: Mapped[list["Section"]] = relationship(back_populates="board", cascade="all, delete-orphan", passive_deletes=True)