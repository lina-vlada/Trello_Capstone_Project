from sqlalchemy import ForeignKey, String, Boolean
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.board import Board
    from entities.ticket import Ticket

class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100),nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="section", cascade="all, delete-orphan", passive_deletes=True)

    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    board: Mapped["Board"] = relationship(back_populates="sections")