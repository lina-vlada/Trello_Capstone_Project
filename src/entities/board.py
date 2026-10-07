from sqlalchemy import ForeignKey, String
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

    boards_to_user: Mapped[list["BoardUser"]] = relationship(back_populates="board_member")

    board_link: Mapped[list["Section"]] = relationship(back_populates="section_to_board")

