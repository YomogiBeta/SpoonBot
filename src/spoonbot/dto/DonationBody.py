from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class DonationBody(BaseModel, frozen=True):
    user: User
    amount: int
    message: str | None
    time: datetime
