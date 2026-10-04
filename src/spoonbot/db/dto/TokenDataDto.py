from pydantic import BaseModel


class TokenDataDto(BaseModel):
    id: bytes
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
