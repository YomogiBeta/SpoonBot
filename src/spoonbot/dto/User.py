from pydantic import BaseModel


class User(BaseModel, frozen=True):
    id: str
    nickname: str | None
