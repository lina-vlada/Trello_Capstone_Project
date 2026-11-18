from sqlalchemy import Boolean, ForeignKey, String, false
from lib.database.postgres import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.ticket_user import TicketUser
    from entities.section import Section

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100),nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    section: Mapped["Section"] = relationship(back_populates="tickets")

    memberships: Mapped[list["TicketUser"]] = relationship(back_populates="ticket", cascade="all, delete-orphan", passive_deletes=True)

    
