from pydantic import BaseModel

from spoonbot.dto.ChatBody import ChatBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class ChatEvent(BaseModel, frozen=True):
    chat_body: ChatBody
    authorization: SpoonAuthorization
