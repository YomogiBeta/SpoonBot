from pydantic import BaseModel
from uuid_utils import UUID

from spoonbot.enums.TokenStatus import TokenStatus


class SpoonAuthorization(BaseModel):
    id: UUID
    access_token: str
    token_type: str
    expire_at: int
    refresh_expire_at: int
    refresh_token: str
    scope: str
    token_status: TokenStatus
