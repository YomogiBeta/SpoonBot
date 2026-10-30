from datetime import datetime

from pydantic import BaseModel


class DonorDto(BaseModel, frozen=True):
    id: str
    nickname: str | None


class DonationDto(BaseModel, frozen=True):
    user: DonorDto
    stickerName: str
    amount: int
    time: datetime


class DonationResponseDto(BaseModel, frozen=True):
    donations: list[DonationDto]
    nextCursor: str | None
