from pydantic import BaseModel

from spoonbot.dto.PresenceBody import PresenceBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class JoinEvent(BaseModel, frozen=True):
    presence_body: PresenceBody
    authorization: SpoonAuthorization
