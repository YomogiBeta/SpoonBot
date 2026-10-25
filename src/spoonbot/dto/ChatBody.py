from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class ChatBody(BaseModel, frozen=True):
    user: User
    isDj: bool
    message: str
    sentTime: datetime
