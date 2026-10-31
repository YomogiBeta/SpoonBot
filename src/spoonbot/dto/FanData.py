from pydantic import BaseModel


class Fan(BaseModel, frozen=True):
    id: str
    nickname: str
    rank: int
    spoonCount: int | None


class FanData(BaseModel, frozen=True):
    fans: list[Fan]
    totalCount: int
