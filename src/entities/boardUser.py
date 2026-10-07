from sqlalchemy import ForeignKey, String, Boolean, Enum
from database.database import Base, RolesEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.user import User
    from entities.board import Board


class BoardUser(Base):
    __tablename__ = "boards_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    member: Mapped["User"] = relationship(back_populates="users_to_board")

    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id"),primary_key=True)
    board_member: Mapped["Board"] = relationship(back_populates="boards_to_user")

    role: Mapped[RolesEnum] = mapped_column(Enum(RolesEnum), nullable=False)



