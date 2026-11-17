from pydantic import BaseModel, ConfigDict, Field


class SectionBase(BaseModel):
	name: str = Field(min_length=1, max_length=100)
	description: str | None = Field(default=None, max_length=300)


class SectionCreate(SectionBase):
	pass


class SectionUpdate(SectionBase):
	name: str | None = Field(default=None, min_length=1, max_length=100)


class TicketResponse(BaseModel):
	id: int
	name: str
	description: str
	is_archived: bool
	section_id: int

	model_config = ConfigDict(from_attributes=True)


class SectionResponse(SectionBase):
	id: int
	is_archived: bool
	board_id: int
	tickets: list[TicketResponse]

	model_config = ConfigDict(from_attributes=True)
