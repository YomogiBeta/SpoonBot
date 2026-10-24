from aiohttp.web_request import Request
from aiohttp.web_response import Response, json_response
from aiohttp.web_routedef import RouteTableDef

from spoonbot.spoon_bot import SpoonBot

routes = RouteTableDef()


class SpoonBotController:
    spoon_bot: SpoonBot

    def __init__(self, spoon_bot: SpoonBot) -> None:
        self.spoon_bot = spoon_bot

        routes.get("/api/csrf-token")(self.csrf_token_function())
        routes.post("/api/bot/invite")(self.bot_invite_request_handler())

    def csrf_token_function(self):
        async def csrf_token_handler(request: Request) -> Response:
            session_id = request.cookies.get("session_id")
            assert session_id is not None, "Unauthorize"
            csrf_token = await self.spoon_bot.regenerate_csrf_token(session_id)
            response = json_response({"csrf_token": csrf_token})
            return response

        return csrf_token_handler

    def bot_invite_request_handler(self):
        async def bot_invite_request(request: Request) -> Response:
            session_id = request.cookies.get("session_id")
            csrf_token = request.headers.get("X-CSRF-TOKEN")
            assert session_id is not None, "Unauthorize"
            assert csrf_token is not None, "Bad Request. Need X-CSRF-TOKEN"
            await self.spoon_bot.start_stream_by_session(session_id, csrf_token)
            response = Response(status=204)
            return response

        return bot_invite_request

    def get_route(self) -> RouteTableDef:
        return routes
