import time

from pydantic import BaseModel

from spoonbot.enums.TokenStatus import TokenStatus

TOKEN_EXPIRE_SECONDS_LEAST = 60 * 10
REFRESH_TOKEN_EXPIRE_SECONDS_LEAST = 60 * 60 * 24
END_REFRESH_TOKEN_SECONDS = 10


class SpoonAuthorization(BaseModel, frozen=True):
    id: str
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

    def valid_refresh_token(self) -> bool:
        epoch_second = int(time.time())
        diff = self.refresh_expire_at - epoch_second
        return diff > REFRESH_TOKEN_EXPIRE_SECONDS_LEAST

    def end_refresh_token(self) -> bool:
        epoch_second = int(time.time())
        diff = self.refresh_expire_at - epoch_second
        return diff <= END_REFRESH_TOKEN_SECONDS
