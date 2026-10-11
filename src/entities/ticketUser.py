from sqlalchemy import ForeignKey, Enum
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
import enum

if TYPE_CHECKING:
    from entities.user import User
    from entities.ticket import Ticket

class TicketRole(enum.Enum):
    CREATOR = "creator"
    MEMBER = "member"

class TicketUser(Base):
    __tablename__ = "tickets_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="ticket_memberships")

    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True)
    ticket: Mapped["Ticket"] = relationship(back_populates="memberships")

    role: Mapped[TicketRole] = mapped_column(Enum(TicketRole, native_enum=False, length=10), nullable=False)