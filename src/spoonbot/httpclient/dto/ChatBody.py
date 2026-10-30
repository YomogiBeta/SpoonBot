from pydantic import BaseModel


class ChatBody(BaseModel, frozen=True):
    message: str
