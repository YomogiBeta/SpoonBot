import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_exceptions import HTTPFound
from aiohttp.web_routedef import RouteDef, RouteTableDef

from spoonbot.constants import DEFAULT_SESSION_EXPIRES_IN
from spoonbot.controller.SpoonOAuthController import SpoonOAuthController, logger
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl


def make_request(
    path: str,
    cookies: dict[str, str] | None = None,
) -> web.Request:
    headers = {}
    if cookies:
        headers["Cookie"] = "; ".join(
            f"{key}={value}" for key, value in cookies.items()
        )
    return make_mocked_request("GET", path, headers=headers)


class OAuthControllerTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.spoon_bot: Any = MagicMock()
        self.spoon_bot.user_authorize_url = MagicMock(
            return_value=AuthorizeUrl(
                "https://authorize.example.com",
                "state-value",
            )
        )
        self.spoon_bot.get_authorization = AsyncMock()
        self.spoon_bot.save_authorization = AsyncMock()
        self.spoon_bot.save_session = AsyncMock()

        self.routes_patcher = patch(
            "spoonbot.controller.SpoonOAuthController.routes",
            new=RouteTableDef(),
        )
        self.routes = self.routes_patcher.start()
        self.addCleanup(self.routes_patcher.stop)

        self.controller = SpoonOAuthController(self.spoon_bot)


class RouteTest(OAuthControllerTestBase):
    def test_registers_oauth_routes(self) -> None:
        self.assertEqual(
            [
                (route.method, route.path)
                for route in self.controller.get_route()
                if isinstance(route, RouteDef)
            ],
            [
                ("GET", "/oauth"),
                ("GET", "/oauth/callback"),
            ],
        )


class RedirectAuthorizationUrlTest(OAuthControllerTestBase):
    async def test_redirects_and_sets_signed_state_cookie(self) -> None:
        handler = self.controller.redirect_authorization_url_handler()
        request = make_request("/oauth")

        response = await handler(request)

        self.assertIsInstance(response, HTTPFound)
        self.assertEqual(response.location, "https://authorize.example.com")
        self.spoon_bot.user_authorize_url.assert_called_once_with()

        cookie = response.cookies["signed_state"]
        self.assertEqual(cookie.value, "state-value")
        self.assertEqual(cookie["max-age"], "180")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertTrue(cookie["secure"])


class GetTokenViaOAuthTest(OAuthControllerTestBase):
    async def test_saves_authorization_and_sets_session_cookie(self) -> None:
        authorization = object()
        self.spoon_bot.get_authorization.return_value = authorization
        self.spoon_bot.save_session.return_value = "session-id"
        handler = self.controller.get_token_via_oauth_handler()
        request = make_request(
            "/oauth/callback?code=one-time-code&state=signed-state",
            cookies={"signed_state": "cookie-state"},
        )

        response = await handler(request)

        self.assertIsInstance(response, HTTPFound)
        self.assertEqual(response.location, "/spoonbot/success")
        self.spoon_bot.get_authorization.assert_awaited_once_with(
            "one-time-code",
            "cookie-state",
            "signed-state",
        )
        self.spoon_bot.save_authorization.assert_awaited_once_with(authorization)
        self.spoon_bot.save_session.assert_awaited_once_with(authorization)

        session_cookie = response.cookies["session_id"]
        self.assertEqual(session_cookie.value, "session-id")
        self.assertEqual(session_cookie["max-age"], str(DEFAULT_SESSION_EXPIRES_IN))
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(session_cookie["samesite"], "Lax")
        self.assertTrue(session_cookie["secure"])
        self.assertEqual(response.cookies["signed_state"]["max-age"], "0")

    async def test_redirects_to_fail_page_and_clears_cookie_on_error(self) -> None:
        self.spoon_bot.get_authorization.side_effect = RuntimeError("oauth failed")
        handler = self.controller.get_token_via_oauth_handler()
        request = make_request(
            "/oauth/callback?code=one-time-code&state=signed-state",
            cookies={"signed_state": "cookie-state"},
        )

        with patch.object(logger, "exception") as log_exception:
            response = await handler(request)

        self.assertIsInstance(response, HTTPFound)
        self.assertEqual(response.location, "/spoonbot/fail")
        self.spoon_bot.save_authorization.assert_not_awaited()
        self.spoon_bot.save_session.assert_not_awaited()
        self.assertEqual(response.cookies["signed_state"]["max-age"], "0")
        log_exception.assert_called_once()
        self.assertIsInstance(log_exception.call_args.args[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
