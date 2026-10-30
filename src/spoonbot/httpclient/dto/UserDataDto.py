from pydantic import BaseModel


class UserDataDto(BaseModel, frozen=True):
    userId: str
