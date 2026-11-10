from pydantic import BaseModel

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class ConnectEvent(BaseModel, frozen=True):
    authorization: SpoonAuthorization
    reconnect: bool = False
