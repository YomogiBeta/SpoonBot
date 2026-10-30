from pydantic import BaseModel


class TokenResponse(BaseModel, frozen=True):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
