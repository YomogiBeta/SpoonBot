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

    encoded_session_id: bytes | None = None
    csrf_token: bytes | None = None


class SessionDataDto(BaseModel):
    id: bytes
    authorization_spoon_user_id: bytes
    encoded_session_id: bytes
    csrf_token: bytes | None = None
