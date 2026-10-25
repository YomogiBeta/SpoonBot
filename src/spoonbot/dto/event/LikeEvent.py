from pydantic import BaseModel

from spoonbot.dto.LikeBody import LikeBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class LikeEvent(BaseModel, frozen=True):
    like_body: LikeBody
    authorization: SpoonAuthorization
