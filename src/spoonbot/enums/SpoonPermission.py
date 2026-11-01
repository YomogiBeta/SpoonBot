from enum import StrEnum


class SpoonPermission(StrEnum):
    READ_ME = "me.read"
    LIVE_READ = "live.read"
    LISTENERS_READ = "listeners.read"
    FANS_READ = "fans.read"
    EVENTS_CHAT = "events.chat"
    EVENTS_PRESENCE = "events.presence"
    EVENTS_LIKE = "events.like"
    EVENTS_DONATION = "events.donation"
    EVENTS_FOLLOW = "events.follow"
    CHAT_SEND = "chat.send"
    DJ_FOLLOW = "dj.follow"
    DONATIONS_READ = "donations.read"
