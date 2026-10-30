import base64

from spoonbot.dto.ChatBody import ChatBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.httpclient.APIClient import APIClient
from spoonbot.httpclient.dto.FanResponseDto import FanResponseDto
from spoonbot.httpclient.dto.ListenersResponseDto import ListenersResponseDto
from spoonbot.httpclient.dto.LiveRoomDto import LiveRoomDto
from spoonbot.httpclient.dto.TokenResponse import TokenResponse
from spoonbot.httpclient.dto.UserDataDto import UserDataDto


class SpoonApiClient(APIClient):
    client_id: str
    client_secret: str

    def initialize(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_token(self, code: str, redirect_uri: str) -> TokenResponse:
        return await self._post(
            endpoint="oauth/token",
            body={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Authorization": self._authorize_client_token()},
            response_type=TokenResponse,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        return await self._post(
            endpoint="oauth/token",
            body={"grant_type": "refresh_token", "refresh_token": refresh_token},
            headers={"Authorization": self._authorize_client_token()},
            response_type=TokenResponse,
        )

    async def get_token_owner_user(self, access_token: str) -> UserDataDto:
        return await self._get(
            endpoint="me",
            headers={"Authorization": self._authorize_token_by_raw_token(access_token)},
            response_type=UserDataDto,
        )

    async def get_live(self, authorization: SpoonAuthorization) -> LiveRoomDto:
        return await self._get(
            endpoint="live",
            headers={"Authorization": self._authorize_token(authorization)},
            response_type=LiveRoomDto,
        )

    async def get_live_listeners(
        self, cursor: str | None, authorization: SpoonAuthorization
    ) -> ListenersResponseDto:
        return await self._get(
            endpoint="live/listeners",
            queries={"cursor": cursor} if cursor is not None else None,
            headers={"Authorization": self._authorize_token(authorization)},
            response_type=ListenersResponseDto,
        )

    async def get_live_fans(self, authorization: SpoonAuthorization) -> FanResponseDto:
        return await self._get(
            endpoint="live/fans",
            headers={"Authorization": self._authorize_token(authorization)},
            response_type=FanResponseDto,
        )

    async def get_live_donations(
        self, cursor: str | None, authorization: SpoonAuthorization
    ) -> ListenersResponseDto:
        return await self._get(
            endpoint="live/donations",
            queries={"cursor": cursor} if cursor is not None else None,
            headers={"Authorization": self._authorize_token(authorization)},
            response_type=ListenersResponseDto,
        )

    async def send_chat(
        self, chat_body: ChatBody, authorization: SpoonAuthorization
    ) -> bool:
        return await self._post_no_content(
            endpoint="live/chat",
            body=chat_body.model_dump(),
            headers={
                "Authorization": self._authorize_token(authorization),
                "Content-Type": "application/json",
            },
        )

    async def follow_dj(self, authorization: SpoonAuthorization) -> bool:
        return await self._post_no_content(
            endpoint="live/follow",
            body=None,
            headers={
                "Authorization": self._authorize_token(authorization),
                "Content-Type": "application/json",
            },
        )

    def stream_live(self, authorization: SpoonAuthorization):
        return self._sse_stream(
            "live/events",
            headers={"Authorization": self._authorize_token(authorization)},
        )

    def _authorize_client_token(self) -> str:
        token_str = f"{self.client_id}:{self.client_secret}"
        token = base64.b64encode(token_str.encode("utf-8")).decode("utf-8")
        return f"Basic {token}"

    def _authorize_token(self, authorization: SpoonAuthorization) -> str:
        return self._authorize_token_by_raw_token(authorization.access_token)

    def _authorize_token_by_raw_token(self, access_token: str) -> str:
        return f"Bearer {access_token}"
