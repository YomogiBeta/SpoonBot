import base64
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self, cast
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientSession

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.exception.ChatRoomCrowdedException import ChatRoomCrowdedException
from spoonbot.httpclient.dto.APIResponse import APIResponse
from spoonbot.httpclient.dto.ChatSendRequestBody import ChatSendRequestBody
from spoonbot.httpclient.dto.DonationResponseDto import DonationResponseDto
from spoonbot.httpclient.dto.FanResponseDto import FanResponseDto
from spoonbot.httpclient.dto.ListenersResponseDto import ListenersResponseDto
from spoonbot.httpclient.dto.LiveRoomDto import LiveRoomDto
from spoonbot.httpclient.dto.TokenResponse import TokenResponse
from spoonbot.httpclient.dto.UserDataDto import UserDataDto
from spoonbot.httpclient.SpoonApiClient import (
    TOO_MANY_CHAT_IN_ROOM_CODE,
    SpoonApiClient,
)

NOW = 4_000_000_000


def make_authorization(access_token: str = "access-token") -> SpoonAuthorization:
    return SpoonAuthorization(
        id="user-1",
        access_token=access_token,
        token_type="Bearer",
        expire_at=NOW + 100_000,
        refresh_expire_at=NOW + 1_000_000,
        refresh_token="refresh-token",
        scope="scope",
        token_status=TokenStatus.DEFAULT,
    )


class FakeHeaders:
    def __init__(self, headers: dict[str, list[str]]) -> None:
        self._headers = headers

    def to_dict(self) -> dict[str, list[str]]:
        return self._headers


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        json_data: Any = None,
        headers: dict[str, list[str]] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.json = AsyncMock(return_value=json_data)
        self.headers = FakeHeaders(headers or {})
        self.raise_for_status = MagicMock()
        if raise_error is not None:
            self.raise_for_status.side_effect = raise_error

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


@dataclass
class PostCall:
    endpoint: str
    json_body: Any
    data: Any
    headers: dict[str, str] | None


class FakeSession:
    def __init__(self) -> None:
        self.response = FakeResponse()
        self.calls: list[PostCall] = []

    def post(
        self,
        endpoint: str,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            PostCall(
                endpoint=endpoint,
                json_body=json,
                data=data,
                headers=headers,
            )
        )
        return self.response


class SpoonApiClientTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.client = SpoonApiClient(
            cast(ClientSession, self.session),
            "https://api.example.com",
        )
        self.client.initialize("client-id", "client-secret")
        self.authorization = make_authorization()


class InitializeTest(SpoonApiClientTestBase):
    def test_stores_client_credentials(self) -> None:
        self.assertEqual(self.client.client_id, "client-id")
        self.assertEqual(self.client.client_secret, "client-secret")

    def test_builds_basic_authorization_header(self) -> None:
        encoded = base64.b64encode(b"client-id:client-secret").decode("utf-8")

        self.assertEqual(
            self.client._authorize_client_token(),
            f"Basic {encoded}",
        )

    def test_builds_bearer_authorization_headers(self) -> None:
        self.assertEqual(
            self.client._authorize_token_by_raw_token("access-token"),
            "Bearer access-token",
        )
        self.assertEqual(
            self.client._authorize_token(self.authorization),
            "Bearer access-token",
        )


class TokenTest(SpoonApiClientTestBase):
    async def test_get_token_posts_authorization_code(self) -> None:
        response = APIResponse(
            body=TokenResponse(
                access_token="access-token",
                token_type="Bearer",
                expires_in=3600,
                refresh_token="refresh-token",
                scope="scope",
            ),
            headers={},
        )

        with patch.object(
            self.client,
            "_post_form",
            new=AsyncMock(return_value=response),
        ) as post_form:
            result = await self.client.get_token("code", "https://redirect.example.com")

        self.assertIs(result, response)
        post_form.assert_awaited_once_with(
            endpoint="oauth/token",
            body={
                "grant_type": "authorization_code",
                "code": "code",
                "redirect_uri": "https://redirect.example.com",
            },
            headers={"Authorization": self.client._authorize_client_token()},
            response_type=TokenResponse,
        )

    async def test_refresh_token_posts_refresh_token(self) -> None:
        response = APIResponse(
            body=TokenResponse(
                access_token="access-token",
                token_type="Bearer",
                expires_in=3600,
                refresh_token="new-refresh-token",
                scope="scope",
            ),
            headers={},
        )

        with patch.object(
            self.client,
            "_post_form",
            new=AsyncMock(return_value=response),
        ) as post_form:
            result = await self.client.refresh_token("refresh-token")

        self.assertIs(result, response)
        post_form.assert_awaited_once_with(
            endpoint="oauth/token",
            body={
                "grant_type": "refresh_token",
                "refresh_token": "refresh-token",
            },
            headers={"Authorization": self.client._authorize_client_token()},
            response_type=TokenResponse,
        )

    async def test_get_token_owner_user_gets_me(self) -> None:
        response = APIResponse(body=UserDataDto(userId="user-1"), headers={})

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_token_owner_user("access-token")

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="me",
            headers={"Authorization": "Bearer access-token"},
            response_type=UserDataDto,
        )


class LiveTest(SpoonApiClientTestBase):
    async def test_get_live_gets_live_endpoint(self) -> None:
        response = APIResponse(
            body=LiveRoomDto(
                liveId=1,
                title="Live",
                startedAt=datetime(2026, 1, 1, tzinfo=UTC),
                closeAirTime=datetime(2026, 1, 2, tzinfo=UTC),
                listenerCount=1,
                totalListenerCount=2,
                welcomeMessage="Welcome",
                isChatFrozen=False,
                categories=[],
                tags=[],
            ),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live(self.authorization)

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live",
            headers={"Authorization": "Bearer access-token"},
            response_type=LiveRoomDto,
        )

    async def test_get_live_listeners_without_cursor(self) -> None:
        response = APIResponse(
            body=ListenersResponseDto(listeners=[], nextCursor=None),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live_listeners(self.authorization)

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live/listeners",
            queries=None,
            headers={"Authorization": "Bearer access-token"},
            response_type=ListenersResponseDto,
        )

    async def test_get_live_listeners_with_cursor(self) -> None:
        response = APIResponse(
            body=ListenersResponseDto(listeners=[], nextCursor=None),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live_listeners(
                self.authorization,
                "next-cursor",
            )

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live/listeners",
            queries={"cursor": "next-cursor"},
            headers={"Authorization": "Bearer access-token"},
            response_type=ListenersResponseDto,
        )

    async def test_get_live_fans_gets_fans_endpoint(self) -> None:
        response = APIResponse(
            body=FanResponseDto(fans=[], totalCount=0),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live_fans(self.authorization)

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live/fans",
            headers={"Authorization": "Bearer access-token"},
            response_type=FanResponseDto,
        )

    async def test_get_live_donations_without_cursor(self) -> None:
        response = APIResponse(
            body=DonationResponseDto(donations=[], nextCursor=None),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live_donations(self.authorization)

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live/donations",
            queries=None,
            headers={"Authorization": "Bearer access-token"},
            response_type=DonationResponseDto,
        )

    async def test_get_live_donations_with_cursor(self) -> None:
        response = APIResponse(
            body=DonationResponseDto(donations=[], nextCursor=None),
            headers={},
        )

        with patch.object(
            self.client,
            "_get",
            new=AsyncMock(return_value=response),
        ) as get:
            result = await self.client.get_live_donations(
                self.authorization,
                "next-cursor",
            )

        self.assertIs(result, response)
        get.assert_awaited_once_with(
            endpoint="live/donations",
            queries={"cursor": "next-cursor"},
            headers={"Authorization": "Bearer access-token"},
            response_type=DonationResponseDto,
        )

    def test_stream_live_builds_sse_stream(self) -> None:
        sentinel = object()

        with patch.object(
            self.client,
            "_sse_stream",
            return_value=sentinel,
        ) as sse_stream:
            result = self.client.stream_live(self.authorization)

        self.assertIs(result, sentinel)
        sse_stream.assert_called_once_with(
            "live/events",
            headers={"Authorization": "Bearer access-token"},
        )


class ChatTest(SpoonApiClientTestBase):
    async def test_send_chat_posts_json_and_returns_true(self) -> None:
        self.session.response = FakeResponse(
            status=200,
            headers={"X-Test": ["1"]},
        )
        chat_body = ChatSendRequestBody(message="hello")

        result = await self.client.send_chat(chat_body, self.authorization)

        self.assertEqual(len(self.session.calls), 1)
        call = self.session.calls[0]
        self.assertEqual(call.endpoint, "live/chat")
        self.assertEqual(call.json_body, {"message": "hello"})
        self.assertIsNone(call.data)
        self.assertEqual(
            call.headers,
            {
                "Authorization": "Bearer access-token",
                "Content-Type": "application/json",
            },
        )
        self.session.response.raise_for_status.assert_called_once_with()
        self.assertEqual(
            result,
            APIResponse(body=True, headers={"X-Test": ["1"]}),
        )

    async def test_send_chat_raises_when_chat_room_is_crowded(self) -> None:
        self.session.response = FakeResponse(
            status=429,
            json_data={"detailCode": TOO_MANY_CHAT_IN_ROOM_CODE},
        )

        with self.assertRaises(ChatRoomCrowdedException):
            await self.client.send_chat(
                ChatSendRequestBody(message="hello"),
                self.authorization,
            )

        self.session.response.json.assert_awaited_once_with()
        self.session.response.raise_for_status.assert_not_called()

    async def test_send_chat_raises_for_other_too_many_requests(self) -> None:
        error = RuntimeError("too many requests")
        self.session.response = FakeResponse(
            status=429,
            json_data={"detailCode": "OTHER"},
            raise_error=error,
        )

        with self.assertRaises(RuntimeError):
            await self.client.send_chat(
                ChatSendRequestBody(message="hello"),
                self.authorization,
            )

        self.session.response.raise_for_status.assert_called_once_with()

    async def test_send_chat_ignores_missing_response_body(self) -> None:
        error = RuntimeError("too many requests")
        self.session.response = FakeResponse(
            status=429,
            json_data=None,
            raise_error=error,
        )

        with self.assertRaises(RuntimeError):
            await self.client.send_chat(
                ChatSendRequestBody(message="hello"),
                self.authorization,
            )

        self.session.response.raise_for_status.assert_called_once_with()

    async def test_follow_dj_posts_no_content(self) -> None:
        response = APIResponse(body=True, headers={})

        with patch.object(
            self.client,
            "_post_no_content",
            new=AsyncMock(return_value=response),
        ) as post_no_content:
            result = await self.client.follow_dj(self.authorization)

        self.assertIs(result, response)
        post_no_content.assert_awaited_once_with(
            endpoint="live/follow",
            body=None,
            headers={
                "Authorization": "Bearer access-token",
                "Content-Type": "application/json",
            },
        )


if __name__ == "__main__":
    unittest.main()
