from pydantic import BaseModel


class TokenDataDto(BaseModel):
    id: bytes
    access_token: str
    token_type: str
    expire_at: int
    refresh_token: str
    refresh_expire_at: int
    scope: str
    token_status: str
