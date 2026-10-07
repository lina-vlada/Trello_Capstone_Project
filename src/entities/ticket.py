from sqlalchemy import ForeignKey, String
from database.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.ticketUser import TicketUser
    from entities.section import Section

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100),nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)

    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    ticket_to_section: Mapped["Section"] = relationship(back_populates="section_link")

    tickets_users: Mapped[list["TicketUser"]] = relationship(back_populates="ticket")

