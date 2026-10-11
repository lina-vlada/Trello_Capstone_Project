from sqlalchemy import String, Boolean
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
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    last_name: Mapped[str] = mapped_column(String(100),nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255),nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    board_memberships: Mapped[list["BoardUser"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    ticket_memberships: Mapped[list["TicketUser"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)