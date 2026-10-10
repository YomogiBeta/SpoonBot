import time

from pydantic import BaseModel
from uuid_utils import UUID

from spoonbot.enums.TokenStatus import TokenStatus

TOKEN_EXPIRE_SECONDS_LEAST = 60 * 10


class SpoonAuthorization(BaseModel):
    id: UUID
    access_token: str
    token_type: str
    expire_at: int
    refresh_expire_at: int
    refresh_token: str
    scope: str
    token_status: TokenStatus

    def valid_access_token(self) -> bool:
        epoch_second = int(time.time())
        diff = self.expire_at - epoch_second
        return diff > TOKEN_EXPIRE_SECONDS_LEAST
