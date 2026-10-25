from pydantic import BaseModel

from spoonbot.dto.FollowBody import FollowBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class FollowEvent(BaseModel, frozen=True):
    follow_body: FollowBody
    authorization: SpoonAuthorization
