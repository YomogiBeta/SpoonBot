from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef

from spoonbot.spoon_bot import SpoonBot

routes = RouteTableDef()


class SpoonBotController:
    spoon_bot: SpoonBot

    def __init__(self, spoon_bot: SpoonBot) -> None:
        self.spoon_bot = spoon_bot

        routes.get("/bot/invite")(self.bot_invite_page_handler())

    def bot_invite_page_handler(self):
        async def bot_invite_page(request: Request) -> Response:
            session_id = request.cookies.get("session_id")
            assert session_id is not None, "Unauthorize"
            csrf_token = await self.spoon_bot.regenerate_csrf_token(session_id)
            response = Response(
                text="今すぐライブにbotを招待しましょう",
                headers={"X-CSRF-TOKNE": csrf_token},
            )
            return response

        return bot_invite_page

    def get_route(self) -> RouteTableDef:
        return routes
