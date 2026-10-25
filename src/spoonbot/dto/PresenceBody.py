from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from spoonbot.dto.User import User


class PresenceType(StrEnum):
    JOIN = "JOIN"


class PresenceBody(BaseModel, frozen=True):
    user: User
    type: PresenceType
    fanRank: int | None
    isManager: bool
    favoriteTemperature: float | None
    time: datetime
