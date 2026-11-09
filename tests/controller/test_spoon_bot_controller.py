import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_exceptions import HTTPForbidden, HTTPUnauthorized
from aiohttp.web_routedef import RouteDef, RouteTableDef

from spoonbot.controller.SpoonBotController import SpoonBotController


def make_request(
    method: str,
    path: str,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> web.Request:
    request_headers = dict(headers or {})
    if cookies:
        request_headers["Cookie"] = "; ".join(
            f"{key}={value}" for key, value in cookies.items()
        )
    return make_mocked_request(method, path, headers=request_headers)


class BotControllerTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.spoon_bot: Any = MagicMock()
        self.spoon_bot.regenerate_csrf_token = AsyncMock()
        self.spoon_bot.get_bot_operation_page = MagicMock()
        self.spoon_bot.get_bot_name = MagicMock()
        self.spoon_bot.start_stream_by_session = AsyncMock()

        self.routes_patcher = patch(
            "spoonbot.controller.SpoonBotController.routes",
            new=RouteTableDef(),
        )
        self.routes = self.routes_patcher.start()
        self.addCleanup(self.routes_patcher.stop)

        self.controller = SpoonBotController(self.spoon_bot)


class RouteTest(BotControllerTestBase):
    def test_registers_bot_routes(self) -> None:
        self.assertEqual(
            [
                (route.method, route.path)
                for route in self.controller.get_route()
                if isinstance(route, RouteDef)
            ],
            [
                ("GET", "/api/v1/csrf-token"),
                ("GET", "/api/v1/bot"),
                ("POST", "/api/v1/bot/invite"),
            ],
        )


class CsrfTokenTest(BotControllerTestBase):
    async def test_requires_session_cookie(self) -> None:
        handler = self.controller.csrf_token_function()
        request = make_request("GET", "/api/v1/csrf-token")

        with self.assertRaises(HTTPUnauthorized):
            await handler(request)

        self.spoon_bot.regenerate_csrf_token.assert_not_awaited()

    async def test_returns_new_csrf_token(self) -> None:
        self.spoon_bot.regenerate_csrf_token.return_value = "new-csrf-token"
        handler = self.controller.csrf_token_function()
        request = make_request(
            "GET",
            "/api/v1/csrf-token",
            cookies={"session_id": "session-id"},
        )

        response = await handler(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.text or "{}"),
            {"csrf_token": "new-csrf-token"},
        )
        self.spoon_bot.regenerate_csrf_token.assert_awaited_once_with("session-id")


class BotInformationTest(BotControllerTestBase):
    async def test_returns_bot_information(self) -> None:
        self.spoon_bot.get_bot_name.return_value = "My Bot"
        self.spoon_bot.get_bot_operation_page.return_value = "/spoonbot/page"
        handler = self.controller.bot_information_function()
        request = make_request("GET", "/api/v1/bot")

        response = await handler(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(
            json.loads(response.text or "{}"),
            {"bot_name": "My Bot", "page": "/spoonbot/page"},
        )
        self.spoon_bot.get_bot_name.assert_called_once_with()
        self.spoon_bot.get_bot_operation_page.assert_called_once_with()

    async def test_returns_null_page_when_not_configured(self) -> None:
        self.spoon_bot.get_bot_name.return_value = "My Bot"
        self.spoon_bot.get_bot_operation_page.return_value = None
        handler = self.controller.bot_information_function()
        request = make_request("GET", "/api/v1/bot")

        response = await handler(request)

        self.assertEqual(
            json.loads(response.text or "{}"),
            {"bot_name": "My Bot", "page": None},
        )


class BotInviteTest(BotControllerTestBase):
    async def test_requires_session_cookie(self) -> None:
        handler = self.controller.bot_invite_request_handler()
        request = make_request(
            "POST",
            "/api/v1/bot/invite",
            headers={"X-CSRF-TOKEN": "csrf-token"},
        )

        with self.assertRaises(HTTPUnauthorized):
            await handler(request)

        self.spoon_bot.start_stream_by_session.assert_not_awaited()

    async def test_requires_csrf_token_header(self) -> None:
        handler = self.controller.bot_invite_request_handler()
        request = make_request(
            "POST",
            "/api/v1/bot/invite",
            cookies={"session_id": "session-id"},
        )

        with self.assertRaises(HTTPForbidden):
            await handler(request)

        self.spoon_bot.start_stream_by_session.assert_not_awaited()

    async def test_returns_no_content_when_connection_is_added(self) -> None:
        self.spoon_bot.start_stream_by_session.return_value = True
        handler = self.controller.bot_invite_request_handler()
        request = make_request(
            "POST",
            "/api/v1/bot/invite",
            cookies={"session_id": "session-id"},
            headers={"X-CSRF-TOKEN": "csrf-token"},
        )

        response = await handler(request)

        self.assertEqual(response.status, 204)
        self.spoon_bot.start_stream_by_session.assert_awaited_once_with(
            "session-id",
            "csrf-token",
        )

    async def test_returns_conflict_when_connection_already_exists(self) -> None:
        self.spoon_bot.start_stream_by_session.return_value = False
        handler = self.controller.bot_invite_request_handler()
        request = make_request(
            "POST",
            "/api/v1/bot/invite",
            cookies={"session_id": "session-id"},
            headers={"X-CSRF-TOKEN": "csrf-token"},
        )

        response = await handler(request)

        self.assertEqual(response.status, 409)


if __name__ == "__main__":
    unittest.main()
