import unittest
from dataclasses import dataclass
from typing import Any, Self, cast
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import ClientResponse, ClientSession, ClientTimeout
from pydantic import BaseModel

from spoonbot.httpclient.APIClient import APIClient


class BodyDto(BaseModel):
    id: int
    name: str


class TestClient(APIClient):
    pass


class FakeHeaders:
    def __init__(self, headers: dict[str, list[str]]) -> None:
        self._headers = headers

    def to_dict(self) -> dict[str, list[str]]:
        return self._headers


class FakeResponse:
    def __init__(
        self,
        json_data: Any = None,
        headers: dict[str, list[str]] | None = None,
        json_error: Exception | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.json = AsyncMock(return_value=json_data)
        if json_error is not None:
            self.json.side_effect = json_error
        self.headers = FakeHeaders(headers or {})
        self.raise_for_status = MagicMock()
        if raise_error is not None:
            self.raise_for_status.side_effect = raise_error

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


@dataclass
class RequestCall:
    method: str
    endpoint: str
    params: dict[str, Any] | None = None
    json_body: Any = None
    data: Any = None
    headers: dict[str, str] | None = None


class FakeSession:
    def __init__(self) -> None:
        self.response = FakeResponse()
        self.calls: list[RequestCall] = []
        self.close_calls = 0

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            RequestCall(method="GET", endpoint=endpoint, params=params, headers=headers)
        )
        return self.response

    def post(
        self,
        endpoint: str,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            RequestCall(
                method="POST",
                endpoint=endpoint,
                json_body=json,
                data=data,
                headers=headers,
            )
        )
        return self.response

    async def close(self) -> None:
        self.close_calls += 1


class APIClientTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.client = TestClient(
            cast(ClientSession, self.session), "https://api.example.com"
        )


class InitTest(APIClientTestBase):
    def test_stores_session(self) -> None:
        self.assertIs(self.client._get_session(), self.session)

    def test_normalizes_base_url_with_trailing_slash(self) -> None:
        cases = [
            ("https://api.example.com", "https://api.example.com/"),
            ("https://api.example.com/", "https://api.example.com/"),
            ("https://api.example.com///", "https://api.example.com/"),
        ]

        for base_url, expected in cases:
            with self.subTest(base_url=base_url):
                client = TestClient(cast(ClientSession, self.session), base_url)
                self.assertEqual(client._base_url, expected)


class CreateTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_builds_session_and_returns_client(self) -> None:
        with (
            patch(
                "spoonbot.httpclient.APIClient.aiohttp.TCPConnector"
            ) as connector_cls,
            patch("spoonbot.httpclient.APIClient.aiohttp.ClientSession") as session_cls,
        ):
            client = await TestClient.create("https://api.example.com/")

        connector_cls.assert_called_once_with()
        session_cls.assert_called_once_with(
            base_url="https://api.example.com/",
            connector=connector_cls.return_value,
        )
        self.assertIs(client._session, session_cls.return_value)
        self.assertEqual(client._base_url, "https://api.example.com/")


class CloseTest(APIClientTestBase):
    async def test_close_closes_session(self) -> None:
        await self.client.close()

        self.assertEqual(self.session.close_calls, 1)


class ResponseBodyTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_json_body(self) -> None:
        response = FakeResponse(json_data={"id": 1, "name": "spoon"})

        result = await APIClient.response_body(cast(ClientResponse, response))

        self.assertEqual(result, {"id": 1, "name": "spoon"})

    async def test_returns_none_on_value_error(self) -> None:
        response = FakeResponse(json_error=ValueError("invalid json"))

        result = await APIClient.response_body(cast(ClientResponse, response))

        self.assertIsNone(result)

    async def test_returns_none_on_client_error(self) -> None:
        response = FakeResponse(json_error=aiohttp.ClientError("boom"))

        result = await APIClient.response_body(cast(ClientResponse, response))

        self.assertIsNone(result)


class GetTest(APIClientTestBase):
    async def test_get_sends_params_and_headers_and_parses_response(self) -> None:
        self.session.response = FakeResponse(
            json_data={"id": 1, "name": "spoon"},
            headers={"X-Test": ["1"]},
        )
        headers = {"Authorization": "Bearer token"}

        result = await self.client._get(
            "users",
            BodyDto,
            queries={"cursor": "next"},
            headers=headers,
        )

        self.assertEqual(len(self.session.calls), 1)
        call = self.session.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertEqual(call.endpoint, "users")
        self.assertEqual(call.params, {"cursor": "next"})
        self.assertEqual(call.headers, headers)
        self.session.response.raise_for_status.assert_called_once_with()
        self.session.response.json.assert_awaited_once_with()
        self.assertEqual(result.body, BodyDto(id=1, name="spoon"))
        self.assertEqual(result.headers, {"X-Test": ["1"]})

    async def test_get_raises_before_parsing_body_on_http_error(self) -> None:
        self.session.response = FakeResponse(raise_error=aiohttp.ClientError("boom"))

        with self.assertRaises(aiohttp.ClientError):
            await self.client._get("users", BodyDto)

        self.session.response.raise_for_status.assert_called_once_with()
        self.session.response.json.assert_not_awaited()


class PostTest(APIClientTestBase):
    async def test_post_sends_json_body_and_parses_response(self) -> None:
        self.session.response = FakeResponse(json_data={"id": 1, "name": "spoon"})
        body = {"name": "spoon"}
        headers = {"Authorization": "Bearer token"}

        result = await self.client._post("users", body, BodyDto, headers=headers)

        self.assertEqual(len(self.session.calls), 1)
        call = self.session.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.endpoint, "users")
        self.assertEqual(call.json_body, body)
        self.assertEqual(call.headers, headers)
        self.assertEqual(result.body, BodyDto(id=1, name="spoon"))


class PostFormTest(APIClientTestBase):
    async def test_post_form_sends_data_body_and_parses_response(self) -> None:
        self.session.response = FakeResponse(json_data={"id": 1, "name": "spoon"})
        body = {"grant_type": "authorization_code"}
        headers = {"Authorization": "Basic token"}

        result = await self.client._post_form(
            "oauth/token", body, BodyDto, headers=headers
        )

        self.assertEqual(len(self.session.calls), 1)
        call = self.session.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.endpoint, "oauth/token")
        self.assertEqual(call.data, body)
        self.assertIsNone(call.json_body)
        self.assertEqual(call.headers, headers)
        self.assertEqual(result.body, BodyDto(id=1, name="spoon"))


class PostNoContentTest(APIClientTestBase):
    async def test_post_no_content_returns_true_without_parsing_body(self) -> None:
        self.session.response = FakeResponse(
            json_data={"ignored": True}, headers={"X-Test": ["1"]}
        )
        headers = {"Content-Type": "application/json"}

        result = await self.client._post_no_content(
            "live/follow", None, headers=headers
        )

        self.assertEqual(len(self.session.calls), 1)
        call = self.session.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.endpoint, "live/follow")
        self.assertIsNone(call.json_body)
        self.assertEqual(call.headers, headers)
        self.session.response.raise_for_status.assert_called_once_with()
        self.session.response.json.assert_not_awaited()
        self.assertEqual(result.body, True)
        self.assertEqual(result.headers, {"X-Test": ["1"]})


class SseStreamTest(APIClientTestBase):
    def test_sse_stream_builds_event_source(self) -> None:
        headers = {"Authorization": "Bearer token"}
        sentinel = object()

        with patch(
            "spoonbot.httpclient.APIClient.sse_client.EventSource",
            return_value=sentinel,
        ) as event_source:
            result = self.client._sse_stream("live/events", headers=headers)

        self.assertIs(result, sentinel)
        event_source.assert_called_once()
        args, kwargs = event_source.call_args
        self.assertEqual(args[0], "https://api.example.com/live/events")
        self.assertIs(kwargs["session"], self.session)
        self.assertEqual(kwargs["headers"], headers)
        self.assertTrue(kwargs["raise_for_status"])
        timeout = kwargs["timeout"]
        self.assertIsInstance(timeout, ClientTimeout)
        self.assertIsNone(timeout.total)


if __name__ == "__main__":
    unittest.main()
