import argparse
import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import time
from urllib.parse import urlparse

import uuid_utils as uuid
from aiohttp import web
from aiohttp.web_exceptions import (
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPUnauthorized,
)
from itsdangerous import TimestampSigner
from oauthlib.oauth2 import WebApplicationClient

from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.constants import (
    DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
    DEFAULT_SESSION_EXPIRES_IN,
    SPACE,
)
from spoonbot.controller.SpoonBotController import SpoonBotController
from spoonbot.controller.SpoonBotWebController import SpoonBotWebController
from spoonbot.controller.SpoonOAuthController import SpoonOAuthController
from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.dto.TokenDataDto import SessionDataDto, TokenDataDto
from spoonbot.db.SpoonUserRepository import SpoonUserRepository
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient
from spoonbot.manager.SpoonEventStreamManager import SpoonEventStreamManager
from spoonbot.types.callback_types import (
    ChatFuncType,
    DonationFuncType,
    FollowFuncType,
    LikeFuncType,
    PresenceFuncType,
)

logger = logging.getLogger(__name__)

STATE_SIZE = 24
OAUTH_STATE_SIGNE_SALT = "oauth-state-verification"


class SpoonBot:
    def __init__(
        self,
        permissions: set[SpoonPermission] | None = None,
        spoon_client_id: str | None = None,
        spoon_client_secret: str | None = None,
        secret_key: str | None = None,
        oauth_redirect_url: str | None = None,
        country: Country | None = None,
        mysql_config: MySQLConfig | None = None,
        bot_name: str = "Spoon Bot",
        bot_operation_page: str | None = None,
    ):
        self.permissions = permissions or set()
        self.permissions.add(SpoonPermission.READ_ME)
        # EventStream を使うためには、streamの権限が1つ以上必要なため、必ず likeを要求
        self.permissions.add(SpoonPermission.EVENTS_LIKE)
        self.spoon_client_id = os.getenv("SPOON_CLIENT_ID", spoon_client_id)
        self.spoon_client_secret = os.getenv("SPOON_CLIENR_SECRET", spoon_client_secret)
        self.secret_key = os.getenv("SPOON_SECRET_KEY", secret_key)
        self.oauth_redirect_url = os.getenv(
            "SPOON_OAUTH_REDIRECT_URL", oauth_redirect_url or ""
        )
        self.target_country = Country(os.getenv("SPOON_BOT_COUNTRY", country))
        self.bot_name = os.getenv("SPOON_BOT_NAME", bot_name)
        self.mysql_config = mysql_config
        self.bot_operation_page = self._normalize_page_target(bot_operation_page)

        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.spoon_client_secret is not None, "Required SPOON_CLIENR_SECRET"
        assert self.secret_key is not None, "Required SPOON_SECRET_KEY"
        assert len(self.secret_key) > 64, (
            "SPOON_SECRET_KEY must be at least 64 characters long."
        )
        assert len(self.oauth_redirect_url) > 0, "Required SPOON_OAUTH_REDIRECT_URL"
        assert self.target_country is not None, "Required SPOON_BOT_COUNTRY"

        self.constants = ConstantsConfig.create(self.target_country)

        self.signer = TimestampSigner(self.secret_key, salt=OAUTH_STATE_SIGNE_SALT)
        self.web_application = web.Application()
        self.web_application.on_startup.append(self.startup_function())
        self.web_application.on_cleanup.append(self.cleanup_function())
        self.spoon_oauth_controller = SpoonOAuthController(self)
        self.spoon_bot_controller = SpoonBotController(self)
        self.web_application.add_routes(
            [
                *self.spoon_oauth_controller.get_route(),
                *self.spoon_bot_controller.get_route(),
                *SpoonBotWebController().get_route(),
            ]
        )
        self.spoon_event_stream_manager = SpoonEventStreamManager(
            self.web_application, self.api_client, self
        )
        self.oauth_client = WebApplicationClient(self.spoon_client_id)

    async def init(self):
        assert self.spoon_client_id is not None
        assert self.spoon_client_secret is not None

        self.api_client = await SpoonApiClient.create(self.constants.api_base_url)
        self.api_client.initialize(self.spoon_client_id, self.spoon_client_secret)
        self.spoon_user_repository = SpoonUserRepository()
        await self.spoon_user_repository.initialize(self.mysql_config)

    def user_authorize_url(self) -> AuthorizeUrl:
        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"

        state = secrets.token_urlsafe(STATE_SIZE)
        signed_state = self.signer.sign(state.encode("utf-8")).decode("utf-8")

        url, _, _ = self.oauth_client.prepare_authorization_request(
            self.constants.oauth_authorize_base_url,
            redirect_url=self.oauth_redirect_url,
            scope=SPACE.join(self.permissions),
            state=signed_state,
        )
        # PKCE implementation is required.
        # However, Spoon developers have not implemented PKCE on their OAuth server.
        # There’s nothing I can do about this.
        return AuthorizeUrl(url, state)

    async def get_authorization(
        self, code: str | None, state: str | None, signed_state: str | None
    ) -> SpoonAuthorization:
        if code is None or len(code) <= 0:
            raise HTTPUnauthorized(
                reason="UnAuthorization: oauth one time code is none or empty"
            )
        if state is None or len(state) <= 0:
            raise HTTPUnauthorized(reason="UnAuthorization:  state is none or empty")

        state_of_session = self.signer.unsign(signed_state or "", max_age=60 * 3)
        if state != state_of_session:
            raise HTTPForbidden(reason="Forbidden: Invalid state parameter.")

        token_respons = await self.api_client.get_token(code, self.oauth_redirect_url)
        user_data = await self.api_client.get_token_owner_user(
            token_respons.access_token
        )
        epoch_second = int(time.time())
        return SpoonAuthorization(
            id=user_data.userId,
            access_token=token_respons.access_token,
            token_type=token_respons.token_type,
            expire_at=epoch_second + token_respons.expires_in,
            refresh_expire_at=epoch_second + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
            refresh_token=token_respons.refresh_token,
            scope=token_respons.scope,
            token_status=TokenStatus.DEFAULT,
        )

    async def get_authorization_by_refresh_token(
        self, authorization: SpoonAuthorization
    ) -> SpoonAuthorization:
        if authorization.end_refresh_token():
            raise HTTPUnauthorized(reason="UnAuthorization: refresh token is invalid")
        token_respons = await self.api_client.refresh_token(authorization.refresh_token)
        epoch_second = int(time.time())
        return SpoonAuthorization(
            id=authorization.id,
            access_token=token_respons.access_token,
            token_type=token_respons.token_type,
            expire_at=epoch_second + token_respons.expires_in,
            refresh_expire_at=epoch_second + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
            refresh_token=token_respons.refresh_token,
            scope=token_respons.scope,
            token_status=authorization.token_status,
        )

    async def start_stream_by_session(self, session_id: str, x_csrf_token: str):
        encoded_session_id = self._hmac_sha256(session_id)
        result = await self.spoon_user_repository.get_token_data_by_session_id(
            encoded_session_id
        )
        if result is None:
            raise HTTPUnauthorized()
        if result.csrf_token is None:
            raise HTTPForbidden(reason="Denied. CRSF token don't match")
        if result.csrf_token.decode("utf-8") != x_csrf_token:
            raise HTTPForbidden(reason="Denied. CRSF token don't match")

        authorization = SpoonAuthorization(
            id=result.id,
            access_token=result.access_token,
            token_type=result.token_type,
            expire_at=result.expire_at,
            refresh_expire_at=result.refresh_expire_at,
            refresh_token=result.refresh_token,
            scope=result.scope,
            token_status=TokenStatus(result.token_status),
        )
        if authorization.end_refresh_token():
            raise HTTPUnauthorized(reason="UnAuthorization: refresh token is invalid")
        await self.spoon_event_stream_manager.add_connection(authorization)

    async def save_authorization(
        self, authorization: SpoonAuthorization, force_refresh: bool = False
    ) -> bool:
        authorization_dto = TokenDataDto(
            id=authorization.id,
            access_token=authorization.access_token,
            token_type=authorization.token_type,
            expire_at=authorization.expire_at,
            refresh_expire_at=authorization.refresh_expire_at,
            refresh_token=authorization.refresh_token,
            scope=authorization.scope,
            token_status=authorization.token_status,
        )
        result = (
            await self.spoon_user_repository.get_token_data(authorization.id)
            if not force_refresh
            else None
        )
        if result is not None or force_refresh:
            return await self.spoon_user_repository.update_token(authorization_dto)
        return await self.spoon_user_repository.insert_token(authorization_dto)

    async def save_session(self, authorization: SpoonAuthorization) -> str:
        session_id = secrets.token_urlsafe(32)

        expires_at = int(time.time()) + DEFAULT_SESSION_EXPIRES_IN

        session_dto = SessionDataDto(
            id=uuid.uuid7().bytes,
            authorization_spoon_user_id=authorization.id,
            encoded_session_id=self._hmac_sha256(session_id),
            expires_at=expires_at,
        )

        succsess_session_inserted = await self.spoon_user_repository.insert_session(
            session_dto
        )
        if not succsess_session_inserted:
            logger.error("Failed to insert new Session Data.")
            raise HTTPInternalServerError()
        return session_id

    async def get_session(self, session_id: str) -> SessionDataDto | None:
        return await self.spoon_user_repository.get_session_data(
            self._hmac_sha256(session_id)
        )

    async def regenerate_csrf_token(self, session_id: str) -> str:
        csrf_token = secrets.token_urlsafe(32)
        success = await self.spoon_user_repository.update_csrf_token(
            self._hmac_sha256(session_id), csrf_token.encode("utg-8")
        )
        if not success:
            logger.error("Failed to update the CSRF token in the database.")
            raise HTTPInternalServerError()
        return csrf_token

    def _hmac_sha256(self, text: str):
        assert self.secret_key is not None, "Required SPOON_SECRET_KEY"
        return hmac.new(
            self.secret_key.encode("utf-8"),
            text.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    def _normalize_page_target(self, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return value

        # 相対パスの ../ や .. を禁止
        parts = value.split("/")
        if ".." in parts:
            raise argparse.ArgumentTypeError("'..' is not allowed in the path")

        # 末尾に / を補完
        if not value.startswith("/"):
            value = f"/{value}"

        return value

    def get_bot_name(self) -> str:
        return self.bot_name if len(self.bot_name) > 0 else "Spoon bot"

    def get_bot_operation_page(self) -> str | None:
        return self.bot_operation_page

    def startup_function(self):
        async def on_startup(web_application: web.Application):
            await self.init()
            web_application["sse_manager"] = self.spoon_event_stream_manager

        return on_startup

    def cleanup_function(self):
        async def on_cleanup(web_application: web.Application):
            manager: SpoonEventStreamManager = web_application["sse_manager"]
            for task in list(manager.tasks.values()):
                task.cancel()
            if manager.tasks:
                await asyncio.gather(*manager.tasks.values(), return_exceptions=True)
            await self.api_client.close()
            await self.spoon_user_repository.close()

        return on_cleanup

    def start(self):
        web.run_app(self.web_application, host="127.0.0.1", port=8080)

    def chat_event(self, callback: ChatFuncType):
        self.spoon_event_stream_manager.chat_callback_append(callback)

    def join_event(self, callback: PresenceFuncType):
        self.spoon_event_stream_manager.presence_callback_append(callback)

    def like_event(self, callback: LikeFuncType):
        self.spoon_event_stream_manager.like_callback_append(callback)

    def gift_event(self, callback: DonationFuncType):
        self.spoon_event_stream_manager.donation_callback_append(callback)

    def follow_event(self, callback: FollowFuncType):
        self.spoon_event_stream_manager.follow_callback_append(callback)
