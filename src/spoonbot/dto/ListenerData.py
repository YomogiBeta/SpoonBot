from typing import Iterable

from pydantic import BaseModel


class Subscription(BaseModel, frozen=True):
    plan: str


class SpoonListener(BaseModel, frozen=True):
    id: str
    nickname: str
    subscription: Subscription | None


class ListenerData(BaseModel):
    listeners: list[SpoonListener] = []

    def append(self, listener: SpoonListener):
        self.listeners.append(listener)

    def extend(self, listeners: Iterable[SpoonListener]):
        self.extend(listeners)
