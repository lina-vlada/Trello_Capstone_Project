from pydantic import BaseModel, ConfigDict, Field
from entities.ticket_user import TicketRole


class TicketCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=300)
    assignee_ids: list[int] = Field(default_factory=list)


class TicketUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=300)
    assignee_ids: list[int] | None = None
    section_id: int | None = None


class TicketMembershipResponse(BaseModel):
    user_id: int
    role: TicketRole

    model_config = ConfigDict(from_attributes=True)


class TicketResponse(BaseModel):
    id: int
    name: str
    description: str
    is_archived: bool
    section_id: int
    memberships: list[TicketMembershipResponse]

    model_config = ConfigDict(from_attributes=True)