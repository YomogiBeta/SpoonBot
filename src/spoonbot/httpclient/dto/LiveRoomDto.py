from datetime import datetime

from pydantic import BaseModel


class LiveRoomDto(BaseModel, frozen=True):
    liveId: int
    title: str
    startedAt: datetime
    closeAirTime: datetime
    listenerCount: int
    totalListenerCount: int
    welcomeMessage: str
    isChatFrozen: bool
    categories: list[str]
    tags: list[str]
