from pydantic import BaseModel


class SubscriptionDto(BaseModel, frozen=True):
    plan: str


class ListenerDto(BaseModel, frozen=True):
    id: str
    nickname: str
    subscription: SubscriptionDto | None


class ListenersResponseDto(BaseModel, frozen=True):
    listeners: list[ListenerDto]
    nextCursor: str | None
