from sqlalchemy import ForeignKey, Enum
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
import enum

if TYPE_CHECKING:
    from entities.user import User
    from entities.board import Board

class BoardRole(enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

class BoardUser(Base):
    __tablename__ = "boards_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="board_memberships")

    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"),primary_key=True)
    board: Mapped["Board"] = relationship(back_populates="memberships")

    role: Mapped[BoardRole] = mapped_column(Enum(BoardRole, native_enum=False, length=10), nullable=False)