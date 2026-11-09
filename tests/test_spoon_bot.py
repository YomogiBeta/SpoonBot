import argparse
import hashlib
import hmac
import os
import unittest
import warnings
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientResponseError, RequestInfo, web
from aiohttp.web_exceptions import (
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPUnauthorized,
)
from itsdangerous import TimestampSigner
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.constants import (
    DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
    DEFAULT_SESSION_EXPIRES_IN,
)
from spoonbot.db.dto.TokenDataDto import SessionDataDto, TokenDataDto
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.dto.DonationData import Donation, DonationData
from spoonbot.dto.FanData import Fan, FanData
from spoonbot.dto.ListenerData import ListenerData, SpoonListener
from spoonbot.dto.LiveRoom import LiveRoom
from spoonbot.dto.RateLimit import RateLimit
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.dto.User import User
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.exception.BurstRequestException import BurstRequestException
from spoonbot.exception.DailyRequestLimitException import DailyRequestLimitException
from spoonbot.httpclient.dto.ChatSendRequestBody import ChatSendRequestBody
from spoonbot.httpclient.dto.DonationResponseDto import (
    DonationDto,
    DonationResponseDto,
    DonorDto,
)
from spoonbot.httpclient.dto.FanResponseDto import FanDto, FanResponseDto
from spoonbot.httpclient.dto.ListenersResponseDto import (
    ListenerDto,
    ListenersResponseDto,
)
from spoonbot.httpclient.dto.LiveRoomDto import LiveRoomDto
from spoonbot.httpclient.dto.TokenResponse import TokenResponse
from spoonbot.httpclient.dto.UserDataDto import UserDataDto
from spoonbot.spoon_bot import (
    OAUTH_STATE_SIGNE_SALT,
    STATE_SIZE,
    SpoonBot,
    _create_ratelimit,
    _too_request_handling,
    logger,
)

NOW = 4_000_000_000
SECRET_KEY = "s" * 40
CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
REDIRECT_URL = "https://example.com/oauth/callback"


def make_authorization(
    authorization_id: str = "user-1",
    refresh_expire_at: int = NOW + 1_000_000,
    token_status: TokenStatus = TokenStatus.DEFAULT,
) -> SpoonAuthorization:
    return SpoonAuthorization(
        id=authorization_id,
        access_token="access-token",
        token_type="Bearer",
        expire_at=NOW + 100_000,
        refresh_expire_at=refresh_expire_at,
        refresh_token="refresh-token",
        scope="scope",
        token_status=token_status,
    )


def make_token(
    token_id: str = "user-1",
    csrf_token: bytes | None = b"csrf-token",
    refresh_expire_at: int = NOW + 1_000_000,
) -> TokenDataDto:
    return TokenDataDto(
        id=token_id,
        access_token="access-token",
        token_type="Bearer",
        expire_at=NOW + 100_000,
        refresh_expire_at=refresh_expire_at,
        refresh_token="refresh-token",
        scope="scope",
        token_status=TokenStatus.DEFAULT,
        csrf_token=csrf_token,
    )


def make_response_error(
    status: int,
    headers: dict[str, str] | None = None,
    message: str = "error",
) -> ClientResponseError:
    request_headers = CIMultiDict(headers or {})
    url = URL("https://api.example.com/live")
    request_info = RequestInfo(
        url,
        "GET",
        CIMultiDictProxy(request_headers),
        url,
    )
    return ClientResponseError(
        request_info,
        (),
        status=status,
        message=message,
        headers=request_headers,
    )


class FakeApiClient:
    def __init__(self) -> None:
        self.close = AsyncMock()
        self.get_token = AsyncMock()
        self.get_token_owner_user = AsyncMock()
        self.refresh_token = AsyncMock()
        self.get_live = AsyncMock()
        self.get_live_listeners = AsyncMock()
        self.get_live_fans = AsyncMock()
        self.get_live_donations = AsyncMock()
        self.send_chat = AsyncMock()
        self.follow_dj = AsyncMock()


class FakeUserRepository:
    def __init__(self) -> None:
        self.initialize = AsyncMock()
        self.close = AsyncMock()
        self.get_token_data = AsyncMock()
        self.get_token_data_by_session_id = AsyncMock()
        self.update_token = AsyncMock()
        self.insert_token = AsyncMock()
        self.insert_session = AsyncMock()
        self.get_session_data = AsyncMock()
        self.update_csrf_token = AsyncMock()


def make_bare_bot() -> SpoonBot:
    bot = SpoonBot.__new__(SpoonBot)
    bot.permissions = {
        SpoonPermission.EVENTS_CHAT,
        SpoonPermission.READ_ME,
        SpoonPermission.CHAT_SEND,
    }
    bot.spoon_client_id = CLIENT_ID
    bot.spoon_client_secret = CLIENT_SECRET
    bot.secret_key = SECRET_KEY
    bot.oauth_redirect_url = REDIRECT_URL
    bot.port = 8080
    bot.target_country = Country.JP
    bot.constants = ConstantsConfig.create(Country.JP)
    bot.bot_name = "Spoon Bot"
    bot.mysql_config = None
    bot.bot_operation_page = None
    bot.signer = TimestampSigner(SECRET_KEY, salt=OAUTH_STATE_SIGNE_SALT)
    bot.web_application = web.Application()
    bot.spoon_event_stream_manager = MagicMock()
    bot.oauth_client = MagicMock()
    bot.api_client = MagicMock()
    bot.spoon_user_repository = MagicMock()
    return bot


class BotFixtureMixin:
    def setUp(self) -> None:
        cast(Any, super()).setUp()
        self.print_patcher = patch("builtins.print")
        self.print_mock = self.print_patcher.start()
        cast(Any, self).addCleanup(self.print_patcher.stop)

        self.api_client: Any = FakeApiClient()
        self.repository: Any = FakeUserRepository()
        self.event_stream_manager: Any = MagicMock()
        self.event_stream_manager.init = AsyncMock()
        self.event_stream_manager.add_connection = AsyncMock()

        self.bot = make_bare_bot()
        self.bot.api_client = self.api_client
        self.bot.spoon_user_repository = self.repository
        self.bot.spoon_event_stream_manager = self.event_stream_manager

    def construct_bot(
        self,
        env: dict[str, str] | None = None,
        **overrides: Any,
    ) -> SpoonBot:
        kwargs: dict[str, Any] = {
            "spoon_client_id": CLIENT_ID,
            "spoon_client_secret": CLIENT_SECRET,
            "secret_key": SECRET_KEY,
            "oauth_redirect_url": REDIRECT_URL,
            "country": Country.JP,
        }
        kwargs.update(overrides)
        with patch.dict(os.environ, env or {}, clear=True):
            return SpoonBot(**kwargs)


class SyncBotTest(BotFixtureMixin, unittest.TestCase):
    pass


class AsyncBotTest(BotFixtureMixin, unittest.IsolatedAsyncioTestCase):
    pass


class CreateRateLimitTest(unittest.TestCase):
    def test_parses_rate_limit_headers(self) -> None:
        headers = CIMultiDict(
            {
                "x-ratelimit-remaining": "9",
                "x-ratelimit-replenish-rate": "8",
                "x-ratelimit-burst-capacity": "7",
                "x-ratelimit-daily-limit": "6",
                "x-ratelimit-daily-remaining": "5",
                "x-ratelimit-daily-reset": "4",
                "x-ratelimit-daily-scope": "live",
            }
        )

        result = _create_ratelimit(headers)

        self.assertEqual(
            result,
            RateLimit(
                remaining=9,
                replenish_rate=8,
                burst_capacity=7,
                daily_limit=6,
                daily_remaining=5,
                daily_reset_epoch=4,
                daily_limited_scope="live",
            ),
        )

    def test_uses_defaults_for_missing_headers(self) -> None:
        result = _create_ratelimit(CIMultiDict())

        self.assertEqual(
            result,
            RateLimit(
                remaining=-1,
                replenish_rate=-1,
                burst_capacity=-1,
                daily_limit=-1,
                daily_remaining=-1,
                daily_reset_epoch=-1,
                daily_limited_scope=None,
            ),
        )


class TooRequestHandlingTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_wrapped_result(self) -> None:
        @_too_request_handling
        async def returns(value: int) -> int:
            return value

        self.assertEqual(await returns(42), 42)

    async def test_raises_daily_limit_when_retry_after_is_present(self) -> None:
        error = make_response_error(
            429,
            headers={
                "retry-after": "60",
                "x-ratelimit-remaining": "0",
            },
        )

        @_too_request_handling
        async def raises() -> None:
            raise error

        with self.assertRaises(DailyRequestLimitException) as context:
            await raises()

        self.assertEqual(context.exception.token_ratelimit.remaining, 0)
        self.assertIn("https://api.example.com/live", str(context.exception))

    async def test_raises_burst_limit_without_retry_after(self) -> None:
        error = make_response_error(
            429,
            headers={"x-ratelimit-remaining": "1"},
        )

        @_too_request_handling
        async def raises() -> None:
            raise error

        with self.assertRaises(BurstRequestException) as context:
            await raises()

        self.assertEqual(context.exception.token_ratelimit.remaining, 1)

    async def test_returns_none_for_other_response_errors(self) -> None:
        error = make_response_error(500)

        @_too_request_handling
        async def raises() -> None:
            raise error

        self.assertIsNone(await raises())


class ConstructorTest(SyncBotTest):
    def test_stores_dependencies_and_default_permissions(self) -> None:
        bot = self.construct_bot()

        self.assertEqual(bot.spoon_client_id, CLIENT_ID)
        self.assertEqual(bot.spoon_client_secret, CLIENT_SECRET)
        self.assertEqual(bot.secret_key, SECRET_KEY)
        self.assertEqual(bot.oauth_redirect_url, REDIRECT_URL)
        self.assertEqual(bot.port, 8080)
        self.assertEqual(bot.target_country, Country.JP)
        self.assertEqual(bot.bot_name, "Spoon Bot")
        self.assertIsNone(bot.mysql_config)
        self.assertIsNone(bot.bot_operation_page)
        self.assertEqual(
            bot.constants.api_base_url,
            "https://jp-openapi.spooncast.net/v1/",
        )
        self.assertEqual(
            bot.constants.oauth_authorize_base_url,
            "https://developers.spooncast.net/jp/oauth/authorize",
        )
        self.assertEqual(
            bot.permissions,
            {
                SpoonPermission.EVENTS_CHAT,
                SpoonPermission.READ_ME,
                SpoonPermission.CHAT_SEND,
            },
        )
        self.assertIsNotNone(bot.spoon_event_stream_manager)
        self.assertGreater(len(bot.web_application.router.routes()), 0)
        self.assertEqual(bot.oauth_client.client_id, CLIENT_ID)

    def test_adds_required_permissions_to_given_permissions(self) -> None:
        bot = self.construct_bot(permissions={SpoonPermission.LIVE_READ})

        self.assertEqual(
            bot.permissions,
            {
                SpoonPermission.LIVE_READ,
                SpoonPermission.EVENTS_CHAT,
                SpoonPermission.READ_ME,
                SpoonPermission.CHAT_SEND,
            },
        )

    def test_environment_variables_override_arguments(self) -> None:
        bot = self.construct_bot(
            env={
                "SPOON_CLIENT_ID": "env-id",
                "SPOON_CLIENT_SECRET": "env-secret",
                "SPOON_SECRET_KEY": "e" * 40,
                "SPOON_OAUTH_REDIRECT_URL": "https://env.example.com/callback",
                "SPOON_BOT_PORT": "9999",
                "SPOON_BOT_COUNTRY": "KR",
                "SPOON_BOT_NAME": "Env Bot",
            },
            spoon_client_id="arg-id",
            spoon_client_secret="arg-secret",
            secret_key="a" * 40,
            oauth_redirect_url="https://arg.example.com/callback",
            port=1234,
            country=Country.JP,
            bot_name="Arg Bot",
        )

        self.assertEqual(bot.spoon_client_id, "env-id")
        self.assertEqual(bot.spoon_client_secret, "env-secret")
        self.assertEqual(bot.secret_key, "e" * 40)
        self.assertEqual(bot.oauth_redirect_url, "https://env.example.com/callback")
        self.assertEqual(bot.port, "9999")
        self.assertEqual(bot.target_country, Country.KR)
        self.assertEqual(bot.bot_name, "Env Bot")
        self.assertEqual(
            bot.constants.api_base_url,
            "https://kr-openapi.spooncast.net/v1/",
        )
        self.assertEqual(
            bot.constants.oauth_authorize_base_url,
            "https://developers.spooncast.net/kr/oauth/authorize",
        )

    def test_requires_client_id(self) -> None:
        with self.assertRaisesRegex(AssertionError, "SPOON_CLIENT_ID"):
            self.construct_bot(spoon_client_id=None)

    def test_requires_client_secret(self) -> None:
        with self.assertRaisesRegex(AssertionError, "SPOON_CLIENT_SECRET"):
            self.construct_bot(spoon_client_secret=None)

    def test_requires_secret_key(self) -> None:
        with self.assertRaisesRegex(AssertionError, "SPOON_SECRET_KEY"):
            self.construct_bot(secret_key=None)

    def test_requires_long_secret_key(self) -> None:
        with self.assertRaisesRegex(AssertionError, "at least 32"):
            self.construct_bot(secret_key="short")

    def test_requires_oauth_redirect_url(self) -> None:
        with self.assertRaisesRegex(AssertionError, "SPOON_OAUTH_REDIRECT_URL"):
            self.construct_bot(oauth_redirect_url=None)

    def test_normalizes_operation_page(self) -> None:
        relative = self.construct_bot(bot_operation_page="spoonbot/page")
        absolute = self.construct_bot(
            bot_operation_page="https://example.com/spoonbot/page"
        )

        self.assertEqual(relative.bot_operation_page, "/spoonbot/page")
        self.assertEqual(
            absolute.bot_operation_page,
            "https://example.com/spoonbot/page",
        )

    def test_rejects_parent_directory_in_operation_page(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            self.construct_bot(bot_operation_page="../secret")


class InitTest(AsyncBotTest):
    async def test_initializes_api_manager_and_repository(self) -> None:
        api_client = MagicMock()
        api_client.initialize = MagicMock()
        repository = FakeUserRepository()

        with (
            patch(
                "spoonbot.spoon_bot.SpoonApiClient.create",
                new=AsyncMock(return_value=api_client),
            ) as create_api,
            patch(
                "spoonbot.spoon_bot.SpoonUserRepository",
                return_value=repository,
            ) as repository_cls,
        ):
            await self.bot.init()

        create_api.assert_awaited_once_with(self.bot.constants.api_base_url)
        api_client.initialize.assert_called_once_with(CLIENT_ID, CLIENT_SECRET)
        self.event_stream_manager.init.assert_awaited_once_with(
            self.bot.web_application,
            api_client,
            self.bot,
        )
        repository_cls.assert_called_once_with()
        repository.initialize.assert_awaited_once_with(None)
        self.assertIs(self.bot.api_client, api_client)
        self.assertIs(self.bot.spoon_user_repository, repository)


class UserAuthorizeUrlTest(SyncBotTest):
    def test_builds_signed_state_and_authorization_url(self) -> None:
        oauth_client: Any = self.bot.oauth_client
        oauth_client.prepare_authorization_request.return_value = (
            "https://authorize.example.com",
            {},
            {},
        )

        with patch(
            "spoonbot.spoon_bot.secrets.token_urlsafe",
            return_value="raw-state",
        ) as token_urlsafe:
            result = self.bot.user_authorize_url()

        self.assertEqual(
            result, AuthorizeUrl("https://authorize.example.com", "raw-state")
        )
        token_urlsafe.assert_called_once_with(STATE_SIZE)
        args, kwargs = oauth_client.prepare_authorization_request.call_args
        self.assertEqual(args[0], self.bot.constants.oauth_authorize_base_url)
        self.assertEqual(kwargs["redirect_url"], REDIRECT_URL)
        self.assertEqual(set(kwargs["scope"]), self.bot.permissions)
        signed_state = self.bot.signer.unsign(kwargs["state"], max_age=60 * 3).decode(
            "utf-8"
        )
        self.assertEqual(signed_state, "raw-state")


class GetAuthorizationTest(AsyncBotTest):
    async def test_requires_code(self) -> None:
        for code in (None, ""):
            with (
                self.subTest(code=code),
                self.assertRaises(HTTPUnauthorized),
            ):
                await self.bot.get_authorization(code, "state", "signed")

    async def test_requires_state(self) -> None:
        for state in (None, ""):
            with (
                self.subTest(state=state),
                self.assertRaises(HTTPUnauthorized),
            ):
                await self.bot.get_authorization("code", state, "signed")

    async def test_rejects_mismatched_state(self) -> None:
        signed_state = self.bot.signer.sign(b"other-state").decode("utf-8")

        with self.assertRaises(HTTPForbidden):
            await self.bot.get_authorization("code", "state", signed_state)

    async def test_exchanges_code_and_builds_authorization(self) -> None:
        self.api_client.get_token.return_value = SimpleNamespace(
            body=TokenResponse(
                access_token="new-access-token",
                token_type="Bearer",
                expires_in=3600,
                refresh_token="new-refresh-token",
                scope="scope",
            )
        )
        self.api_client.get_token_owner_user.return_value = SimpleNamespace(
            body=UserDataDto(userId="user-1")
        )

        with patch("spoonbot.spoon_bot.time.time", return_value=NOW):
            signed_state = self.bot.signer.sign(b"state").decode("utf-8")
            result = await self.bot.get_authorization("code", "state", signed_state)

        self.api_client.get_token.assert_awaited_once_with("code", REDIRECT_URL)
        self.api_client.get_token_owner_user.assert_awaited_once_with(
            "new-access-token"
        )
        self.assertEqual(
            result,
            SpoonAuthorization(
                id="user-1",
                access_token="new-access-token",
                token_type="Bearer",
                expire_at=NOW + 3600,
                refresh_expire_at=NOW + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
                refresh_token="new-refresh-token",
                scope="scope",
                token_status=TokenStatus.DEFAULT,
            ),
        )


class GetAuthorizationByRefreshTokenTest(AsyncBotTest):
    async def test_rejects_expired_refresh_token(self) -> None:
        authorization = make_authorization(refresh_expire_at=0)

        with self.assertRaises(HTTPUnauthorized):
            await self.bot.get_authorization_by_refresh_token(authorization)

        self.api_client.refresh_token.assert_not_awaited()

    async def test_refreshes_and_preserves_identity_and_status(self) -> None:
        authorization = make_authorization(token_status=TokenStatus.CHAT_BLOCK)
        self.api_client.refresh_token.return_value = SimpleNamespace(
            body=TokenResponse(
                access_token="refreshed-access-token",
                token_type="Bearer",
                expires_in=7200,
                refresh_token="refreshed-refresh-token",
                scope="scope",
            )
        )

        with patch("spoonbot.spoon_bot.time.time", return_value=NOW):
            result = await self.bot.get_authorization_by_refresh_token(authorization)

        self.api_client.refresh_token.assert_awaited_once_with("refresh-token")
        self.assertEqual(
            result,
            SpoonAuthorization(
                id="user-1",
                access_token="refreshed-access-token",
                token_type="Bearer",
                expire_at=NOW + 7200,
                refresh_expire_at=NOW + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
                refresh_token="refreshed-refresh-token",
                scope="scope",
                token_status=TokenStatus.CHAT_BLOCK,
            ),
        )


class StartStreamBySessionTest(AsyncBotTest):
    async def test_raises_when_session_is_not_found(self) -> None:
        self.repository.get_token_data_by_session_id.return_value = None

        with self.assertRaises(HTTPUnauthorized):
            await self.bot.start_stream_by_session("session-id", "csrf-token")

        self.repository.get_token_data_by_session_id.assert_awaited_once_with(
            self.bot._hmac_sha256("session-id")
        )

    async def test_raises_when_csrf_token_is_missing(self) -> None:
        self.repository.get_token_data_by_session_id.return_value = make_token(
            csrf_token=None
        )

        with self.assertRaises(HTTPForbidden):
            await self.bot.start_stream_by_session("session-id", "csrf-token")

    async def test_raises_when_csrf_token_does_not_match(self) -> None:
        self.repository.get_token_data_by_session_id.return_value = make_token()

        with self.assertRaises(HTTPForbidden):
            await self.bot.start_stream_by_session("session-id", "other-token")

    async def test_raises_when_refresh_token_has_ended(self) -> None:
        self.repository.get_token_data_by_session_id.return_value = make_token(
            refresh_expire_at=0
        )

        with self.assertRaises(HTTPUnauthorized):
            await self.bot.start_stream_by_session("session-id", "csrf-token")

        self.event_stream_manager.add_connection.assert_not_called()

    async def test_adds_connection_with_authorization_from_session(self) -> None:
        self.repository.get_token_data_by_session_id.return_value = make_token()
        self.event_stream_manager.add_connection.return_value = True

        result = await self.bot.start_stream_by_session("session-id", "csrf-token")

        self.assertTrue(result)
        self.event_stream_manager.add_connection.assert_awaited_once_with(
            SpoonAuthorization(
                id="user-1",
                access_token="access-token",
                token_type="Bearer",
                expire_at=NOW + 100_000,
                refresh_expire_at=NOW + 1_000_000,
                refresh_token="refresh-token",
                scope="scope",
                token_status=TokenStatus.DEFAULT,
            )
        )


class SaveAuthorizationTest(AsyncBotTest):
    async def test_inserts_when_authorization_does_not_exist(self) -> None:
        authorization = make_authorization()
        self.repository.get_token_data.return_value = None
        self.repository.insert_token.return_value = True

        result = await self.bot.save_authorization(authorization)

        self.assertTrue(result)
        self.repository.get_token_data.assert_awaited_once_with("user-1")
        self.repository.insert_token.assert_awaited_once()
        self.repository.update_token.assert_not_awaited()

    async def test_updates_when_authorization_exists(self) -> None:
        authorization = make_authorization()
        self.repository.get_token_data.return_value = make_token()
        self.repository.update_token.return_value = True

        result = await self.bot.save_authorization(authorization)

        self.assertTrue(result)
        self.repository.update_token.assert_awaited_once()
        self.repository.insert_token.assert_not_awaited()

    async def test_force_refresh_updates_without_lookup(self) -> None:
        authorization = make_authorization()
        self.repository.update_token.return_value = True

        result = await self.bot.save_authorization(authorization, force_refresh=True)

        self.assertTrue(result)
        self.repository.get_token_data.assert_not_awaited()
        self.repository.update_token.assert_awaited_once()


class SaveSessionTest(AsyncBotTest):
    async def test_inserts_hashed_session_and_returns_raw_id(self) -> None:
        self.repository.insert_session.return_value = True

        with (
            patch(
                "spoonbot.spoon_bot.secrets.token_urlsafe",
                return_value="session-id",
            ) as token_urlsafe,
            patch(
                "spoonbot.spoon_bot.uuid.uuid7",
                return_value=SimpleNamespace(bytes=b"u" * 16),
            ) as uuid7,
            patch("spoonbot.spoon_bot.time.time", return_value=NOW),
        ):
            result = await self.bot.save_session(make_authorization())

        self.assertEqual(result, "session-id")
        token_urlsafe.assert_called_once_with(32)
        uuid7.assert_called_once_with()
        self.repository.insert_session.assert_awaited_once_with(
            SessionDataDto(
                id=b"u" * 16,
                authorization_spoon_user_id="user-1",
                encoded_session_id=self.bot._hmac_sha256("session-id"),
                expires_at=NOW + DEFAULT_SESSION_EXPIRES_IN,
            )
        )

    async def test_raises_internal_server_error_when_insert_fails(self) -> None:
        self.repository.insert_session.return_value = False

        with (
            patch(
                "spoonbot.spoon_bot.secrets.token_urlsafe",
                return_value="session-id",
            ),
            patch.object(logger, "error") as log_error,
            self.assertRaises(HTTPInternalServerError),
        ):
            await self.bot.save_session(make_authorization())

        log_error.assert_called_once_with("Failed to insert new Session Data.")


class GetSessionTest(AsyncBotTest):
    async def test_uses_hashed_session_id(self) -> None:
        session = SessionDataDto(
            id=b"u" * 16,
            authorization_spoon_user_id="user-1",
            encoded_session_id=b"e" * 32,
            expires_at=NOW,
        )
        self.repository.get_session_data.return_value = session

        result = await self.bot.get_session("session-id")

        self.assertIs(result, session)
        self.repository.get_session_data.assert_awaited_once_with(
            self.bot._hmac_sha256("session-id")
        )


class RegenerateCsrfTokenTest(AsyncBotTest):
    async def test_updates_hashed_session_with_new_token(self) -> None:
        self.repository.update_csrf_token.return_value = True

        with patch(
            "spoonbot.spoon_bot.secrets.token_urlsafe",
            return_value="csrf-token",
        ) as token_urlsafe:
            result = await self.bot.regenerate_csrf_token("session-id")

        self.assertEqual(result, "csrf-token")
        token_urlsafe.assert_called_once_with(32)
        self.repository.update_csrf_token.assert_awaited_once_with(
            self.bot._hmac_sha256("session-id"),
            b"csrf-token",
        )

    async def test_raises_internal_server_error_when_update_fails(self) -> None:
        self.repository.update_csrf_token.return_value = False

        with (
            patch(
                "spoonbot.spoon_bot.secrets.token_urlsafe",
                return_value="csrf-token",
            ),
            patch.object(logger, "error") as log_error,
            self.assertRaises(HTTPInternalServerError),
        ):
            await self.bot.regenerate_csrf_token("session-id")

        log_error.assert_called_once_with(
            "Failed to update the CSRF token in the database."
        )


class HmacSha256Test(SyncBotTest):
    def test_returns_hmac_digest(self) -> None:
        expected = hmac.new(
            SECRET_KEY.encode("utf-8"),
            b"text",
            hashlib.sha256,
        ).digest()

        self.assertEqual(self.bot._hmac_sha256("text"), expected)


class GetLiveTest(AsyncBotTest):
    async def test_returns_live_room(self) -> None:
        live_room = LiveRoomDto(
            liveId=1,
            title="Live",
            startedAt=datetime(2026, 1, 1, tzinfo=UTC),
            closeAirTime=datetime(2026, 1, 2, tzinfo=UTC),
            listenerCount=10,
            totalListenerCount=20,
            welcomeMessage="Welcome",
            isChatFrozen=False,
            categories=["talk"],
            tags=["tag"],
        )
        self.api_client.get_live.return_value = SimpleNamespace(
            body=live_room,
            headers={},
        )

        result = await self.bot.get_live(make_authorization())

        self.api_client.get_live.assert_awaited_once()
        self.assertEqual(result, LiveRoom.model_validate(live_room.model_dump()))


class GetLiveListenersTest(AsyncBotTest):
    async def test_fetches_all_pages_and_converts_listeners(self) -> None:
        self.api_client.get_live_listeners.side_effect = [
            SimpleNamespace(
                body=ListenersResponseDto(
                    listeners=[ListenerDto(id="1", nickname="a", subscription=None)],
                    nextCursor="cursor-2",
                )
            ),
            SimpleNamespace(body=ListenersResponseDto(listeners=[], nextCursor=None)),
        ]

        with patch.object(ListenerData, "extend") as extend:
            result = await self.bot.get_live_listeners(make_authorization())

        self.assertIsInstance(result, ListenerData)
        calls = self.api_client.get_live_listeners.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0].args[1])
        self.assertEqual(calls[1].args[1], "cursor-2")
        self.assertEqual(extend.call_count, 2)
        first_listeners = extend.call_args_list[0].args[0]
        self.assertEqual(len(first_listeners), 1)
        self.assertIsInstance(first_listeners[0], SpoonListener)
        self.assertEqual(first_listeners[0].id, "1")
        self.assertEqual(extend.call_args_list[1].args[0], [])


class GetLiveFansTest(AsyncBotTest):
    async def test_returns_fan_data(self) -> None:
        self.api_client.get_live_fans.return_value = SimpleNamespace(
            body=FanResponseDto(
                fans=[FanDto(id="1", nickname="fan", rank=1, spoonCount=10)],
                totalCount=1,
            )
        )

        result = await self.bot.get_live_fans(make_authorization())

        self.assertEqual(
            result,
            FanData(
                fans=[Fan(id="1", nickname="fan", rank=1, spoonCount=10)], totalCount=1
            ),
        )


class GetLiveDonationsTest(AsyncBotTest):
    async def test_fetches_all_pages_and_converts_donations(self) -> None:
        donation_time = datetime(2026, 1, 1, tzinfo=UTC)
        self.api_client.get_live_donations.side_effect = [
            SimpleNamespace(
                body=DonationResponseDto(
                    donations=[
                        DonationDto(
                            user=DonorDto(id="fan-1", nickname="Fan"),
                            stickerName="sticker",
                            amount=100,
                            time=donation_time,
                        )
                    ],
                    nextCursor="cursor-2",
                )
            ),
            SimpleNamespace(body=DonationResponseDto(donations=[], nextCursor=None)),
        ]

        with patch.object(DonationData, "extend") as extend:
            result = await self.bot.get_live_donations(make_authorization())

        self.assertIsInstance(result, DonationData)
        calls = self.api_client.get_live_donations.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0].args[1])
        self.assertEqual(calls[1].args[1], "cursor-2")
        self.assertEqual(extend.call_count, 2)
        first_donations = extend.call_args_list[0].args[0]
        self.assertEqual(len(first_donations), 1)
        self.assertIsInstance(first_donations[0], Donation)
        self.assertEqual(first_donations[0].user, User(id="fan-1", nickname="Fan"))
        self.assertEqual(first_donations[0].amount, 100)
        self.assertEqual(extend.call_args_list[1].args[0], [])


class SendChatTest(AsyncBotTest):
    async def test_returns_false_for_invalid_message(self) -> None:
        result = await self.bot.send_chat("   ", make_authorization())

        self.assertFalse(result)
        self.api_client.send_chat.assert_not_awaited()

    async def test_sends_valid_message(self) -> None:
        authorization = make_authorization()

        result = await self.bot.send_chat(" hello ", authorization)

        self.assertTrue(result)
        self.api_client.send_chat.assert_awaited_once_with(
            ChatSendRequestBody(message="hello"),
            authorization,
        )


class FollowDjTest(AsyncBotTest):
    async def test_returns_api_result(self) -> None:
        authorization = make_authorization()
        self.api_client.follow_dj.return_value = SimpleNamespace(body=True)

        result = await self.bot.follow_dj(authorization)

        self.assertTrue(result)
        self.api_client.follow_dj.assert_awaited_once_with(authorization)


class NormalizePageTargetTest(SyncBotTest):
    def test_normalizes_page_targets(self) -> None:
        cases = [
            (None, None),
            ("https://example.com/page", "https://example.com/page"),
            ("http://example.com/page", "http://example.com/page"),
            ("/spoonbot/page", "/spoonbot/page"),
            ("spoonbot/page", "/spoonbot/page"),
            ("", "/"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.bot._normalize_page_target(value), expected)

    def test_rejects_parent_directory(self) -> None:
        for value in ("..", "../secret", "spoonbot/../secret"):
            with (
                self.subTest(value=value),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                self.bot._normalize_page_target(value)


class BotNameTest(SyncBotTest):
    def test_returns_bot_name(self) -> None:
        self.bot.bot_name = "My Bot"
        self.assertEqual(self.bot.get_bot_name(), "My Bot")

    def test_returns_default_for_empty_name(self) -> None:
        self.bot.bot_name = ""
        self.assertEqual(self.bot.get_bot_name(), "Spoon bot")

    def test_returns_operation_page(self) -> None:
        self.bot.bot_operation_page = "/page"
        self.assertEqual(self.bot.get_bot_operation_page(), "/page")


class StartupFunctionTest(AsyncBotTest):
    async def test_initializes_and_registers_event_stream_manager(self) -> None:
        web_application = web.Application()

        with (
            patch.object(self.bot, "init", new=AsyncMock()) as init,
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await self.bot.startup_function()(web_application)

        init.assert_awaited_once_with()
        self.assertIs(
            web_application["sse_manager"],
            self.bot.spoon_event_stream_manager,
        )
        self.print_mock.assert_called_once_with("Start Spoonbot Server!!")


class CleanupFunctionTest(AsyncBotTest):
    async def test_cancels_tasks_and_closes_clients(self) -> None:
        task1 = MagicMock()
        task2 = MagicMock()
        self.event_stream_manager.tasks = {1: task1, 2: task2}
        web_application = web.Application()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            web_application["sse_manager"] = self.event_stream_manager

        with patch(
            "spoonbot.spoon_bot.asyncio.gather",
            new=AsyncMock(),
        ) as gather:
            await self.bot.cleanup_function()(web_application)

        task1.cancel.assert_called_once_with()
        task2.cancel.assert_called_once_with()
        gather.assert_awaited_once_with(task1, task2, return_exceptions=True)
        self.api_client.close.assert_awaited_once_with()
        self.repository.close.assert_awaited_once_with()


class StartTest(SyncBotTest):
    def test_runs_web_application(self) -> None:
        self.bot.port = 9090

        with patch("spoonbot.spoon_bot.web.run_app") as run_app:
            self.bot.start()

        run_app.assert_called_once_with(
            self.bot.web_application,
            host="127.0.0.1",
            port=9090,
        )


class EventRegistrationTest(SyncBotTest):
    def test_registers_callbacks_on_event_stream_manager(self) -> None:
        callback = MagicMock()
        cases = [
            (self.bot.chat_event, self.event_stream_manager.chat_callback_append),
            (self.bot.join_event, self.event_stream_manager.presence_callback_append),
            (self.bot.like_event, self.event_stream_manager.like_callback_append),
            (self.bot.gift_event, self.event_stream_manager.donation_callback_append),
            (self.bot.follow_event, self.event_stream_manager.follow_callback_append),
        ]

        for register, append in cases:
            with self.subTest(register=register.__name__):
                register(callback)
                append.assert_called_once_with(callback)
                append.reset_mock()


if __name__ == "__main__":
    unittest.main()
