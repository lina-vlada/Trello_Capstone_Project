from sqlalchemy import ForeignKey, String
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.ticketUser import TicketUser
    from entities.boardUser import BoardUser

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100),nullable=False)
    last_name: Mapped[str] = mapped_column(String(100),nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255),nullable=False)

    users_to_board: Mapped[list["BoardUser"]] = relationship(back_populates="member")

    tickets_users: Mapped[list["TicketUser"]] = relationship(back_populates="user")
