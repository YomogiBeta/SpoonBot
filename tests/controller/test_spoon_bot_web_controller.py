import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_exceptions import HTTPNotFound
from aiohttp.web_fileresponse import FileResponse
from aiohttp.web_routedef import RouteDef, RouteTableDef, StaticDef

from spoonbot.controller.SpoonBotWebController import SpoonBotWebController


def make_request(path: str) -> web.Request:
    return make_mocked_request("GET", path)


class WebControllerTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.routes_patcher = patch(
            "spoonbot.controller.SpoonBotWebController.routes",
            new=RouteTableDef(),
        )
        self.routes = self.routes_patcher.start()
        self.addCleanup(self.routes_patcher.stop)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.controller = SpoonBotWebController()


class RouteTest(WebControllerTestBase):
    def test_registers_page_asset_and_root_routes(self) -> None:
        route_defs = {
            (route.method, route.path)
            for route in self.routes
            if isinstance(route, RouteDef)
        }
        static_defs = [
            route.prefix for route in self.routes if isinstance(route, StaticDef)
        ]

        self.assertEqual(
            route_defs,
            {
                ("GET", "/spoonbot/connect"),
                ("GET", "/spoonbot/success"),
                ("GET", "/spoonbot/fail"),
                ("GET", "/spoonbot/invite"),
            },
        )
        self.assertEqual(static_defs, ["/assets/"])


class ServePageTest(WebControllerTestBase):
    async def test_serves_configured_page_file(self) -> None:
        assets_dir = Path(self.temp_dir.name)
        page_path = assets_dir / "connect.html"
        page_path.write_text("connect page", encoding="utf-8")
        request = make_request("/spoonbot/connect")

        with patch(
            "spoonbot.controller.SpoonBotWebController.ASSETS_DIR",
            new=assets_dir,
        ):
            response = await self.controller.serve_page(request)

        self.assertIsInstance(response, FileResponse)
        file_response = cast(FileResponse, response)
        self.assertEqual(file_response.status, 200)
        self.assertEqual(file_response._path, page_path)

    async def test_raises_not_found_when_page_file_is_missing(self) -> None:
        request = make_request("/spoonbot/success")

        with (
            patch(
                "spoonbot.controller.SpoonBotWebController.ASSETS_DIR",
                new=Path(self.temp_dir.name),
            ),
            self.assertRaises(HTTPNotFound),
        ):
            await self.controller.serve_page(request)


if __name__ == "__main__":
    unittest.main()
