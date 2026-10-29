from aiohttp.web_exceptions import HTTPForbidden, HTTPUnauthorized
from aiohttp.web_request import Request
from aiohttp.web_response import Response, json_response
from aiohttp.web_routedef import RouteTableDef

from spoonbot.spoon_bot import SpoonBot

routes = RouteTableDef()


class SpoonBotController:
    spoon_bot: SpoonBot

    def __init__(self, spoon_bot: SpoonBot) -> None:
        self.spoon_bot = spoon_bot

        routes.get("/api/v1/csrf-token")(self.csrf_token_function())
        routes.get("/api/v1/bot-name")(self.bot_name_function())
        routes.post("/api/v1/bot/invite")(self.bot_invite_request_handler())

    def csrf_token_function(self):
        async def csrf_token_handler(request: Request) -> Response:
            session_id = request.cookies.get("session_id")
            if session_id is None:
                raise HTTPUnauthorized()
            csrf_token = await self.spoon_bot.regenerate_csrf_token(session_id)
            return json_response({"csrf_token": csrf_token})

        return csrf_token_handler

    def bot_name_function(self):
        async def bot_name_handler(_: Request) -> Response:
            return json_response({"bot_name": self.spoon_bot.get_bot_name()})

        return bot_name_handler

    def bot_invite_request_handler(self):
        async def bot_invite_request(request: Request) -> Response:
            session_id = request.cookies.get("session_id")
            csrf_token = request.headers.get("X-CSRF-TOKEN")
            if session_id is None:
                raise HTTPUnauthorized()
            if csrf_token is None:
                raise HTTPForbidden(reason="Bad Request. Need X-CSRF-TOKEN")
            await self.spoon_bot.start_stream_by_session(session_id, csrf_token)
            return Response(status=204)

        return bot_invite_request

    def get_route(self) -> RouteTableDef:
        return routes
