from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, Field
from entities.board_user import BoardRole


class BoardBase(BaseModel):
    name: str
    description: str | None = None 

class BoardCreate(BoardBase):
    pass

class BoardUpdate(BoardBase):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None

class BoardResponse(BoardBase):
    id: int 
    is_archived : bool 

    model_config = ConfigDict(from_attributes=True)

class BoardInviteRequest(BaseModel):
    email: str
    role: BoardRole = BoardRole.VIEWER

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any):
        if isinstance(v, str):
            return v.strip().lower()
        return v

class BoardInviteAccept(BaseModel):
    token: str