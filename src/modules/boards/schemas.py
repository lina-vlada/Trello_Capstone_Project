from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator, model_validator, Field
from entities.board_user import BoardRole
from modules.sections.schemas import SectionSummaryResponse


class BoardBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)

class BoardCreate(BoardBase):
    pass

class BoardUpdate(BoardBase):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_null(cls, v):
        if v is None:
            raise ValueError("Board name cannot be null")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self

class BoardResponse(BoardBase):
    id: int 
    is_archived : bool 

    model_config = ConfigDict(from_attributes=True)

class BoardDetailResponse(BoardResponse):
    sections: list[SectionSummaryResponse]

class BoardInviteRequest(BaseModel):
    email: str
    role: BoardRole = BoardRole.VIEWER

    @field_validator("role")
    @classmethod
    def role_must_not_be_owner(cls, value: BoardRole) -> BoardRole:
        if value is BoardRole.OWNER:
            raise ValueError("Invite role must be editor or viewer")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any):
        if isinstance(v, str):
            return v.strip().lower()
        return v

class BoardInviteAccept(BaseModel):
    token: str