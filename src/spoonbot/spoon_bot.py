import argparse
import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import time
from functools import wraps
from http import HTTPStatus
from typing import Callable
from urllib.parse import urlparse

import uuid_utils as uuid
from aiohttp import ClientResponseError, web
from aiohttp.web_exceptions import (
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPUnauthorized,
)
from itsdangerous import TimestampSigner
from multidict import MultiMapping
from oauthlib.oauth2 import WebApplicationClient

from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.constants import (
    DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
    DEFAULT_SESSION_EXPIRES_IN,
)
from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.dto.TokenDataDto import SessionDataDto, TokenDataDto
from spoonbot.db.SpoonUserRepository import SpoonUserRepository
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.dto.DonationData import Donation, DonationData
from spoonbot.dto.FanData import FanData
from spoonbot.dto.ListenerData import ListenerData, SpoonListener
from spoonbot.dto.LiveRoom import LiveRoom
from spoonbot.dto.RateLimit import RateLimit
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.exception.BurstRequestException import BurstRequestException
from spoonbot.exception.DailyRequestLimitException import DailyRequestLimitException
from spoonbot.httpclient.dto.ChatSendRequestBody import ChatSendRequestBody
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient
from spoonbot.types.callback_types import (
    ChatFuncType,
    ConnectFuncType,
    DonationFuncType,
    EndFuncType,
    FollowFuncType,
    LikeFuncType,
    PresenceFuncType,
)

logger = logging.getLogger(__name__)

STATE_SIZE = 24
OAUTH_STATE_SIGNE_SALT = "oauth-state-verification"


def _create_ratelimit(headers: MultiMapping[str]) -> RateLimit:
    return RateLimit(
        remaining=int(headers.get("x-ratelimit-remaining", -1)),
        replenish_rate=int(headers.get("x-ratelimit-replenish-rate", -1)),
        burst_capacity=int(headers.get("x-ratelimit-burst-capacity", -1)),
        daily_limit=int(headers.get("x-ratelimit-daily-limit", -1)),
        daily_remaining=int(headers.get("x-ratelimit-daily-remaining", -1)),
        daily_reset_epoch=int(
            headers.get("x-ratelimit-daily-reset", -1),
        ),
        daily_limited_scope=headers.get("x-ratelimit-daily-scope"),
    )


def _too_request_handling(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ClientResponseError as exception:
            if exception.status == HTTPStatus.TOO_MANY_REQUESTS.value:
                assert exception.headers is not None
                if exception.headers and "retry-after" in (
                    key.lower() for key in exception.headers
                ):
                    raise DailyRequestLimitException(
                        token_ratelimit=_create_ratelimit(exception.headers),
                        url=str(exception.request_info.url),
                    )
                raise BurstRequestException(
                    token_ratelimit=_create_ratelimit(exception.headers),
                    url=str(exception.request_info.url),
                )

    return wrapper


class SpoonBot:
    def __init__(
        self,
        permissions: set[SpoonPermission] | None = None,
        spoon_client_id: str | None = None,
        spoon_client_secret: str | None = None,
        secret_key: str | None = None,
        oauth_redirect_url: str | None = None,
        country: Country | None = None,
        port: int = 8080,
        mysql_config: MySQLConfig | None = None,
        bot_name: str = "Spoon Bot",
        bot_operation_page: str | None = None,
    ):
        print("Started creating Spoonbot.")
        logger.info("Started creating Spoonbot.")
        self.permissions = permissions or set()
        # EventStreamを使うために、streamの権限が1つ以上必要なため、EVENTS_CHATを要求
        self.permissions.add(SpoonPermission.EVENTS_CHAT)
        # トークン管理の際に連携者の情報を取得する必要があるので、READ_MEを要求
        self.permissions.add(SpoonPermission.READ_ME)
        # ユーザーへのFeedback手段がチャット送信しかないため、CHAT_SENDを要求
        self.permissions.add(SpoonPermission.CHAT_SEND)

        self.spoon_client_id = os.getenv("SPOON_CLIENT_ID", spoon_client_id)
        self.spoon_client_secret = os.getenv("SPOON_CLIENT_SECRET", spoon_client_secret)
        self.secret_key = os.getenv("SPOON_SECRET_KEY", secret_key)
        self.oauth_redirect_url = os.getenv(
            "SPOON_OAUTH_REDIRECT_URL", oauth_redirect_url or ""
        )
        self.port = os.getenv("SPOON_BOT_PORT", port)
        self.target_country = Country(os.getenv("SPOON_BOT_COUNTRY", country))
        self.bot_name = os.getenv("SPOON_BOT_NAME", bot_name)
        self.mysql_config = mysql_config
        self.bot_operation_page = self._normalize_page_target(bot_operation_page)

        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.spoon_client_secret is not None, "Required SPOON_CLIENT_SECRET"
        assert self.secret_key is not None, "Required SPOON_SECRET_KEY"
        assert len(self.secret_key) > 32, (
            "SPOON_SECRET_KEY must be at least 32 characters long."
        )
        assert len(self.oauth_redirect_url) > 0, "Required SPOON_OAUTH_REDIRECT_URL"
        assert self.target_country is not None, "Required SPOON_BOT_COUNTRY"

        self.constants = ConstantsConfig.create(self.target_country)

        self.signer = TimestampSigner(self.secret_key, salt=OAUTH_STATE_SIGNE_SALT)
        self.web_application = web.Application()
        self.web_application.on_startup.append(self.startup_function())
        self.web_application.on_cleanup.append(self.cleanup_function())

        # lazy import
        from spoonbot.controller.SpoonBotController import SpoonBotController
        from spoonbot.controller.SpoonBotWebController import SpoonBotWebController
        from spoonbot.controller.SpoonOAuthController import SpoonOAuthController
        from spoonbot.manager.SpoonEventStreamManager import SpoonEventStreamManager

        self.spoon_event_stream_manager = SpoonEventStreamManager()

        self.web_application.add_routes(
            [
                *SpoonOAuthController(self).get_route(),
                *SpoonBotController(self).get_route(),
                *SpoonBotWebController().get_route(),
            ]
        )
        self.oauth_client = WebApplicationClient(self.spoon_client_id)

    async def init(self):
        print("Started initializing Spoonbot.")
        logger.info("Started initializing Spoonbot.")
        assert self.spoon_client_id is not None
        assert self.spoon_client_secret is not None

        self.api_client = await SpoonApiClient.create(self.constants.api_base_url)
        self.api_client.initialize(self.spoon_client_id, self.spoon_client_secret)

        await self.spoon_event_stream_manager.init(
            self.web_application, self.api_client, self
        )

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
            scope=list(self.permissions),
            state=signed_state,
        )
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

        state_of_parameter = self.signer.unsign(
            signed_state or "", max_age=60 * 3
        ).decode("utf-8")
        if state != state_of_parameter:
            raise HTTPForbidden(reason="Forbidden: Invalid state parameter.")

        token_respons = await self.api_client.get_token(code, self.oauth_redirect_url)
        user_data = await self.api_client.get_token_owner_user(
            token_respons.body.access_token
        )
        epoch_second = int(time.time())
        return SpoonAuthorization(
            id=user_data.body.userId,
            access_token=token_respons.body.access_token,
            token_type=token_respons.body.token_type,
            expire_at=epoch_second + token_respons.body.expires_in,
            refresh_expire_at=epoch_second + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
            refresh_token=token_respons.body.refresh_token,
            scope=token_respons.body.scope,
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
            access_token=token_respons.body.access_token,
            token_type=token_respons.body.token_type,
            expire_at=epoch_second + token_respons.body.expires_in,
            refresh_expire_at=epoch_second + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
            refresh_token=token_respons.body.refresh_token,
            scope=token_respons.body.scope,
            token_status=authorization.token_status,
        )

    async def start_stream_by_session(self, session_id: str, x_csrf_token: str) -> bool:
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
        return await self.spoon_event_stream_manager.add_connection(authorization)

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
            self._hmac_sha256(session_id), csrf_token.encode("utf-8")
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

    @_too_request_handling
    async def get_live(self, authorization: SpoonAuthorization) -> LiveRoom:
        result = await self.api_client.get_live(authorization)
        return LiveRoom.model_validate(result.body.model_dump())

    @_too_request_handling
    async def get_live_listeners(
        self, authorization: SpoonAuthorization
    ) -> ListenerData:
        result = ListenerData()
        cursor = None
        while True:
            fetch_data = await self.api_client.get_live_listeners(authorization, cursor)
            result.extend(
                [
                    SpoonListener.model_validate(listener.model_dump())
                    for listener in fetch_data.body.listeners
                ]
            )
            cursor = fetch_data.body.nextCursor
            if cursor is None:
                break
        return result

    @_too_request_handling
    async def get_live_fans(self, authorization: SpoonAuthorization) -> FanData:
        result = await self.api_client.get_live_fans(authorization)
        return FanData.model_validate(result.body.model_dump())

    @_too_request_handling
    async def get_live_donations(
        self, authorization: SpoonAuthorization
    ) -> DonationData:
        result = DonationData()
        cursor = None
        while True:
            fetch_data = await self.api_client.get_live_donations(authorization, cursor)
            result.extend(
                [
                    Donation.model_validate(listener.model_dump())
                    for listener in fetch_data.body.donations
                ]
            )
            cursor = fetch_data.body.nextCursor
            if cursor is None:
                break
        return result

    @_too_request_handling
    async def send_chat(self, message: str, authorization: SpoonAuthorization) -> bool:
        request_body = ChatSendRequestBody(message=message)
        if not request_body.valid_message():
            return False
        await self.api_client.send_chat(request_body, authorization)
        return True

    @_too_request_handling
    async def follow_dj(self, authorization: SpoonAuthorization) -> bool:
        result = await self.api_client.follow_dj(authorization)
        return result.body

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
            print("Start Spoonbot Server!!")
            logger.info("Start Spoonbot Server!!")

        return on_startup

    def cleanup_function(self):
        async def on_cleanup(web_application: web.Application):
            # lazy import
            from spoonbot.manager.SpoonEventStreamManager import SpoonEventStreamManager

            manager: SpoonEventStreamManager = web_application["sse_manager"]
            for task in list(manager.tasks.values()):
                task.cancel()
            if manager.tasks:
                await asyncio.gather(*manager.tasks.values(), return_exceptions=True)
            await self.api_client.close()
            await self.spoon_user_repository.close()

        return on_cleanup

    def start(self):
        assert self.port is not None
        web.run_app(self.web_application, host="127.0.0.1", port=int(self.port))

    def connect_event(self, callback: ConnectFuncType):
        self.spoon_event_stream_manager.connect_callback_append(callback)

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

    def end_event(self, callback: EndFuncType):
        self.spoon_event_stream_manager.end_callback_append(callback)
