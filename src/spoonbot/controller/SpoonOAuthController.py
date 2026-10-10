from aiohttp.web_exceptions import HTTPFound
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef

from spoonbot.spoon_bot import SpoonBot

routes = RouteTableDef()
SIGNED_STATE_KEY = "signed_state"


class SpoonOAuthController:
    spoon_bot: SpoonBot

    def __init__(self, spoon_bot: SpoonBot) -> None:
        self.spoon_bot = spoon_bot

        routes.get("/oauth")(self.redirect_authorization_url_handler())
        routes.get("/oauth/callback")(self.get_token_via_oauth_handler())

    def redirect_authorization_url_handler(self):
        async def redirect_authorization_url(_: Request) -> HTTPFound:
            authorize_url = self.spoon_bot.user_authorize_url()
            response = HTTPFound(location=authorize_url.url)

            response.set_cookie(
                name=SIGNED_STATE_KEY,
                value=authorize_url.state,
                max_age=60 * 3,  # 3分有効
                httponly=True,
                samesite="Lax",
                secure=True,
            )

            return response

        return redirect_authorization_url

    def get_token_via_oauth_handler(self):
        async def get_token_via_oauth(request: Request):
            code = request.query.get("code")
            returned_state = request.query.get("state")
            signed_state = request.cookies.get(SIGNED_STATE_KEY)

            auth = await self.spoon_bot.get_authorization(
                code, returned_state, signed_state
            )
            await self.spoon_bot.save_authorization(auth)

            response = Response(text="Bot連携に成功しました。")
            response.del_cookie(SIGNED_STATE_KEY)

            return response

        return get_token_via_oauth

    def get_route(self) -> RouteTableDef:
        return routes
