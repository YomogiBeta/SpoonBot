from datetime import datetime
from typing import Iterable

from pydantic import BaseModel

from spoonbot.dto.User import User


class Donation(BaseModel, frozen=True):
    user: User
    stickerName: str
    amount: int
    time: datetime


class DonationData(BaseModel):
    donations: list[Donation] = []

    def append(self, donation: Donation):
        self.donations.append(donation)

    def extend(self, donations: Iterable[Donation]):
        self.extend(donations)
