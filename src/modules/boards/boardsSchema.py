from pydantic import BaseModel, ConfigDict


class BoardBase(BaseModel):
    name: str
    description: str | None = None 

class BoardCreate(BoardBase):
    pass

class BoardResponse(BoardBase):
    id: int 

    model_config = ConfigDict(from_attributes=True)