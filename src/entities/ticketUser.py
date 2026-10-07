from sqlalchemy import ForeignKey, String, Enum
from database.database import Base, RolesEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from entities.user import User
    from entities.ticket import Ticket

class TicketUser(Base):
    __tablename__ = "tickets_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="tickets_users")


    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    ticket: Mapped["Ticket"] = relationship(back_populates="tickets_users")


    role: Mapped[RolesEnum] = mapped_column(Enum(RolesEnum), nullable=False)