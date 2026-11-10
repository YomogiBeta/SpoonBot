import sys
from pathlib import Path

from aiohttp.web_exceptions import HTTPNotFound
from aiohttp.web_fileresponse import FileResponse
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse
from aiohttp.web_routedef import RouteTableDef

routes = RouteTableDef()


def _get_base_dir() -> Path:
    # PyInstaller などで実行ファイル化されている場合
    meipass = getattr(sys, "_MEIPASS", None)

    if meipass is not None:
        return Path(meipass)

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # src/spoonbot/controller/xxx.py
    return Path(__file__).resolve().parents[1]


PAGES = {
    "connect": "connect.html",
    "success": "success.html",
    "fail": "fail.html",
    "invite": "invite.html",
}
ASSETS_DIR = _get_base_dir() / "assets"


class SpoonBotWebController:
    def __init__(self) -> None:
        for page in PAGES:
            routes.get(f"/spoonbot/{page}")(self.serve_page)
        routes.static("/assets/", ASSETS_DIR)

    @staticmethod
    async def serve_page(request: Request) -> StreamResponse:
        filename = PAGES[request.path[len("/spoonbot/") :]]
        filepath = ASSETS_DIR / filename

        if not filepath.is_file():
            raise HTTPNotFound()

        return FileResponse(filepath)

    def get_route(self) -> RouteTableDef:
        return routes
