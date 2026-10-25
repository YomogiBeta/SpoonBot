from pydantic import BaseModel

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class EndEvent(BaseModel, frozen=True):
    authorization: SpoonAuthorization
