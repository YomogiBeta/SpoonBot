from pydantic import BaseModel, field_validator


def _utf16_length(string: str) -> int:
    return len(string.encode("utf-16-le")) // 2


MAX_SIZE = 200


class ChatSendRequestBody(BaseModel, frozen=True):
    message: str

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip()

    def valid_message(self) -> bool:
        if not self.message:
            return False
        if _utf16_length(self.message) > 200:
            return False
        return True
