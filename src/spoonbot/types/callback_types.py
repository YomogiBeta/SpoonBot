from typing import Awaitable, Callable

from spoonbot.dto.event.ChatEvent import ChatEvent
from spoonbot.dto.event.DonationEvent import GiftEvent
from spoonbot.dto.event.EndEvent import EndEvent
from spoonbot.dto.event.FollowEvent import FollowEvent
from spoonbot.dto.event.JoinEvent import JoinEvent
from spoonbot.dto.event.LikeEvent import LikeEvent

ChatFuncType = Callable[[ChatEvent], Awaitable[None] | None]
PresenceFuncType = Callable[[JoinEvent], Awaitable[None] | None]
LikeFuncType = Callable[[LikeEvent], Awaitable[None] | None]
DonationFuncType = Callable[[GiftEvent], Awaitable[None] | None]
FollowFuncType = Callable[[FollowEvent], Awaitable[None] | None]
EndFuncType = Callable[[EndEvent], Awaitable[None] | None]
