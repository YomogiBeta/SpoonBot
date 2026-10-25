from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from spoonbot.dto.User import User


class LikeType(StrEnum):
    PAID = "PAID"
    FREE = "FREE"


class LikeBody(BaseModel, frozen=True):
    user: User
    type: LikeType
    totalAmount: int
    amount: int
    extraAmount: int
    combo: int | None
    time: datetime
