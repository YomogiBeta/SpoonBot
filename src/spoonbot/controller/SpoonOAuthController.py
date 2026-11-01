import logging

from aiohttp.web_exceptions import HTTPFound
from aiohttp.web_request import Request
from aiohttp.web_routedef import RouteTableDef

from spoonbot.constants import DEFAULT_SESSION_EXPIRES_IN
from spoonbot.spoon_bot import SpoonBot

routes = RouteTableDef()
SIGNED_STATE_KEY = "signed_state"
logger = logging.getLogger(__name__)


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
            signed_state = request.query.get("state")
            cookie_state = request.cookies.get(SIGNED_STATE_KEY)

            try:
                auth = await self.spoon_bot.get_authorization(
                    code, cookie_state, signed_state
                )
                await self.spoon_bot.save_authorization(auth)
                session_id = await self.spoon_bot.save_session(auth)

                response = HTTPFound(location="/spoonbot/success")
                response.del_cookie(SIGNED_STATE_KEY)
                response.set_cookie(
                    name="session_id",
                    value=session_id,
                    max_age=DEFAULT_SESSION_EXPIRES_IN,
                    httponly=True,
                    samesite="Lax",
                    secure=True,
                )

                return response
            except Exception as exception:
                logger.exception(exception)
                response = HTTPFound(location="/spoonbot/fail")
                response.del_cookie(SIGNED_STATE_KEY)
                return response

        return get_token_via_oauth

    def get_route(self) -> RouteTableDef:
        return routes
