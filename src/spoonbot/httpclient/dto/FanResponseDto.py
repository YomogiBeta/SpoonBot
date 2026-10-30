from pydantic import BaseModel


class FanDto(BaseModel, frozen=True):
    id: str
    nickname: str
    rank: int
    spoonCount: int | None


class FanResponseDto(BaseModel, frozen=True):
    fans: list[FanDto]
    totalCount: int
