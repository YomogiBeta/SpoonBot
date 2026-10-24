from pydantic import BaseModel


class UserDataDto(BaseModel):
    userId: str
