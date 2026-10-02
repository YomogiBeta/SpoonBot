from enum import StrEnum


class SpoonPermission(StrEnum):
    LIVE_READ = "live.read"
    LISTENERS_READ = "listeners.read"
    FANS_READ = "fans.read"
    EVENTS_CHAT = "events.chat"
    EVENTS_PRESENCE = "events.presence"
    EVENTS_LIKE = "events.like"
    EVENTS_DONATION = "events.donation"
    CHAT_SEND = "chat.send"
