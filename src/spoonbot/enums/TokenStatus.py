from enum import StrEnum


class TokenStatus(StrEnum):
    DEFAULT = "DEFAULT"
    CHAT_BLOCK = "CHAT_BLOCK"
    BOT_BLOCK = "BOT_BLOCK"
