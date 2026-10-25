from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class FollowBody(BaseModel, frozen=True):
    user: User
    time: datetime
