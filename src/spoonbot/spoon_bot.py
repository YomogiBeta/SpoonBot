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

    def start(self):
        """SpoonBotサーバーを起動します。

        aiohttpのWebアプリケーションを``127.0.0.1``の設定ポート（デフォルト8080）で
        実行します。このメソッドはサーバーが停止するまでブロックし、OAuthコールバックや
        EventStreamの受信はこのサーバー経由で処理されます。

        ポート番号は SPOON_BOT_PORT 環境変数、
        または 初期化時引数の``port``で変更できます。

        Raises:
            AssertionError: ポートが未設定の場合。
        """
        assert self.port is not None
        web.run_app(self.web_application, host="127.0.0.1", port=int(self.port))

    def connect_event(self, callback: ConnectFuncType):
        """イベントストリームへの接続が確立したときに呼び出されるコールバックを登録します。

        コールバックには``ConnectEvent``が渡されます。``reconnect``属性で初回接続か
        再接続かを判別できます。コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: 接続時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import ConnectEvent

            @spoonbot.connect_event
            async def on_connect(connect_event: ConnectEvent):
                if not connect_event.reconnect:
                    await spoonbot.send_chat(
                        "I'm here!", connect_event.authorization
                    )
            ```
        """
        self.spoon_event_stream_manager.connect_callback_append(callback)

    def chat_event(self, callback: ChatFuncType):
        """ライブのチャットを受信したときに呼び出されるコールバックを登録します。

        コールバックには送信者やメッセージなどのチャット内容と認可情報を含む
        ``ChatEvent``が渡されます。コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: チャット受信時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import ChatEvent

            @spoonbot.chat_event
            async def on_chat(chat_event: ChatEvent):
                if chat_event.chat_body.message == "Hello":
                    await spoonbot.send_chat(
                        f"Hello {chat_event.chat_body.user.nickname}!!",
                        chat_event.authorization,
                    )
            ```
        """
        self.spoon_event_stream_manager.chat_callback_append(callback)

    def join_event(self, callback: PresenceFuncType):
        """リスナーがライブへ入室したときに呼び出されるコールバックを登録します。

        コールバックには入室したユーザーの情報を含む``JoinEvent``が渡されます。
        コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: 入室時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import JoinEvent

            @spoonbot.join_event
            async def on_join(join_event: JoinEvent):
                await spoonbot.send_chat(
                    f"Welcome {join_event.presence_body.user.nickname}!!",
                    join_event.authorization,
                )
            ```
        """
        self.spoon_event_stream_manager.presence_callback_append(callback)

    def like_event(self, callback: LikeFuncType):
        """リスナーが「いいね」を送信したときに呼び出されるコールバックを登録します。

        コールバックには「いいね」を行ったユーザーなどの情報を含む``LikeEvent``が渡されます。
        コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: 「いいね」受信時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import LikeEvent

            @spoonbot.like_event
            async def on_like(like_event: LikeEvent):
                await spoonbot.send_chat(
                    f"Thank you! {like_event.like_body.user.nickname}",
                    like_event.authorization,
                )
            ```
        """
        self.spoon_event_stream_manager.like_callback_append(callback)

    def gift_event(self, callback: DonationFuncType):
        """リスナーがギフト（投げ銭）を送信したときに呼び出されるコールバックを登録します。

        コールバックにはギフトの内容や送信者などを含む``GiftEvent``が渡されます。
        コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: ギフト受信時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import GiftEvent

            @spoonbot.gift_event
            async def on_gift(gift_event: GiftEvent):
                await spoonbot.send_chat(
                    f"Thank you for the gift! "
                    f"{gift_event.donation_body.user.nickname}",
                    gift_event.authorization,
                )
            ```
        """
        self.spoon_event_stream_manager.donation_callback_append(callback)

    def follow_event(self, callback: FollowFuncType):
        """リスナーがDJをフォローしたときに呼び出されるコールバックを登録します。

        コールバックにはフォローしたユーザーの情報などを含む``FollowEvent``が渡されます。
        コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: フォロー時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import FollowEvent

            @spoonbot.follow_event
            async def on_follow(follow_event: FollowEvent):
                await spoonbot.send_chat(
                    f"Thank you for following! "
                    f"{follow_event.follow_body.user.nickname}",
                    follow_event.authorization,
                )
            ```
        """
        self.spoon_event_stream_manager.follow_callback_append(callback)

    def end_event(self, callback: EndFuncType):
        """ライブの配信が終了したときに呼び出されるコールバックを登録します。

        コールバックには終了したライブの認可情報などを含む``EndEvent``が渡されます。
        コールバックは同期・非同期のどちらでも登録できます。

        Args:
            callback: ライブ終了時に実行する関数またはコルーチン関数。

        Examples:
            ```python
            from spoonbot import EndEvent

            @spoonbot.end_event
            async def on_end(end_event: EndEvent):
                print(f"Live ended: {end_event.authorization.id}")
            ```
        """
        self.spoon_event_stream_manager.end_callback_append(callback)

    @_too_request_handling
    async def send_chat(self, message: str, authorization: SpoonAuthorization) -> bool:
        """ライブのチャットへメッセージを送信します。

        送信前にメッセージの妥当性を検証し、無効な場合は送信せず``False``を返します。
        メッセージは UTF-16 code unit 基準で文字数をカウントしたときに、
        200文字を超過している場合、送信されずにfalseとなります。
        これはSpoon Developpers側の制約です。

        送信に成功した場合は``True``を返します。

        Args:
            message: 送信するチャットメッセージ。
            authorization: チャットを送信するユーザーの認可情報。

        Returns:
            bool: メッセージが有効で送信に成功した場合は``True``、無効な場合は
                ``False``。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
            ChatRoomCrowdedException: 同じチャットルーム内で短時間に大量のコメントが
                投稿され、ルーム側の制限に達した場合。Bot自身の送信量ではなく、
                ルーム全体のコメント量が原因です。
            MessageSendUnavailableException: チャット欄が凍結されている、またはBotが
                チャットへのメッセージ送信を禁止されている場合。

        Examples:
            >>> await spoonbot.send_chat("Hello!", chat_event.authorization)
            True
        """
        request_body = ChatSendRequestBody(message=message)
        if not request_body.valid_message():
            return False
        await self.api_client.send_chat(request_body, authorization)
        return True

    @_too_request_handling
    async def get_live(self, authorization: SpoonAuthorization) -> LiveRoom:
        """現在配信中のライブルーム情報を取得します。

        Args:
            authorization: 対象ライブを配信しているDJの認可情報。

        Returns:
            LiveRoom: ライブのタイトルや参加者数などの情報を保持するオブジェクト。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
        """
        result = await self.api_client.get_live(authorization)
        return LiveRoom.model_validate(result.body.model_dump())

    @_too_request_handling
    async def get_live_listeners(
        self, authorization: SpoonAuthorization
    ) -> ListenerData:
        """ライブルームに参加しているリスナーの一覧を取得します。

        APIのページネーションを自動的に辿り、全てのリスナーを1つの``ListenerData``へ
        集約して返します。

        Args:
            authorization: 対象ライブルームのDJの認可情報。

        Returns:
            ListenerData: ライブに参加中のリスナーを保持する一覧オブジェクト。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
        """
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
        """ライブルームのファン情報を取得します。

        Args:
            authorization: 対象ライブルームのDJの認可情報。

        Returns:
            FanData: ライブのファンに関する情報を保持するオブジェクト。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
        """
        result = await self.api_client.get_live_fans(authorization)
        return FanData.model_validate(result.body.model_dump())

    @_too_request_handling
    async def get_live_donations(
        self, authorization: SpoonAuthorization
    ) -> DonationData:
        """ライブルームで行われたギフト（投げ銭）の一覧を取得します。

        APIのページネーションを自動的に辿り、全てのギフトを1つの``DonationData``へ
        集約して返します。

        Args:
            authorization: 対象ライブルームのDJの認可情報。

        Returns:
            DonationData: ライブで送信されたギフトを保持する一覧オブジェクト。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
        """
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
    async def follow_dj(self, authorization: SpoonAuthorization) -> bool:
        """現在配信中のDJをフォローします。

        Args:
            authorization: フォロー操作を行うユーザーの認可情報。

        Returns:
            bool: フォロー処理に成功した場合は``True``。

        Raises:
            BurstRequestException: 短時間のリクエスト上限（バースト制限）に達した場合。
            DailyRequestLimitException: 1日あたりのAPIリクエスト上限に達した場合。
        """
        result = await self.api_client.follow_dj(authorization)
        return result.body

    def get_bot_name(self) -> str:
        """設定されているBot名を取得します。

        Returns:
            str: Bot名。未設定または空文字の場合は``"Spoon bot"``を返します。
        """
        return self.bot_name if len(self.bot_name) > 0 else "Spoon bot"

    def get_bot_operation_page(self) -> str | None:
        """Bot運用ページとして設定されたURLまたはパスを取得します。

        Returns:
            str | None: 設定されたURLもしくはパス。未設定の場合は``None``。
        """
        return self.bot_operation_page

    def user_authorize_url(self) -> AuthorizeUrl:
        """SpoonアカウントとのOAuth連携を開始するための認可URLを生成します。

        推測困難なstate値を生成して署名し、OAuth 2.0の認可リクエストURLを組み立てます。
        返される``AuthorizeUrl.state``は署名前のstate値であり、コールバック時に
        ``get_authorization``へ渡すことで改ざん検知を行います。

        通常、このメソッドをライブラリ利用者が利用することはありません。oauthはライブラリによおってハンドリングされています。
        セッションを高度に制御したい場合のみ利用します。


        Returns:
            AuthorizeUrl: ユーザーをリダイレクトさせる認可URLと、署名前のstate値を
                保持するオブジェクト。

        Raises:
            AssertionError: クライアントIDまたはリダイレクトURLが未設定の場合。

        Examples:
            >>> authorize_url = spoonbot.user_authorize_url()
            >>> print(authorize_url.url)
        """
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
        """OAuthコールバックで受け取った認可コードをトークン情報へ交換します。

        認可コードとstateの妥当性を検証したうえでSpoon APIへトークン交換を要求し、
        アクセストークン・リフレッシュトークン・有効期限などを含む
        ``SpoonAuthorization``を返します。stateは署名付きの値と突き合わせ、
        署名の有効期限は3分です。

        通常、このメソッドをライブラリ利用者が利用することはありません。oauthはライブラリによおってハンドリングされています。
        セッションを高度に制御したい場合のみ利用します。

        Args:
            code: Spoonから返されるワンタイムの認可コード。
            state: 認可リクエスト時に``user_authorize_url``が生成したstate値。
            signed_state: 認可リクエスト時に署名されたstate値。通常はクエリパラメータ
                として返されます。

        Returns:
            SpoonAuthorization: トークン情報とSpoonユーザーIDを保持する認可情報。

        Raises:
            HTTPUnauthorized: 認可コードまたはstateが空の場合。
            HTTPForbidden: stateが署名済みの値と一致しない場合。
            itsdangerous.BadSignature: 署名が不正、または署名の有効期限が切れている
                場合。
        """
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
        """リフレッシュトークンを使って新しい認可情報を取得します。

        保持しているリフレッシュトークンの有効期限が切れている場合は再認可が必要なため
        ``HTTPUnauthorized``を送出します。有効な場合はSpoon APIへトークン更新を要求し、
        同じSpoonユーザーID・トークン状態を引き継いだ新しい``SpoonAuthorization``を返します。

        通常、このメソッドをライブラリ利用者が利用することはありません。トークンの有効期限はライブラリにより管理されています。

        Args:
            authorization: 更新対象の認可情報。

        Returns:
            SpoonAuthorization: 更新後のアクセストークン・リフレッシュトークン・
                有効期限を持つ認可情報。

        Raises:
            HTTPUnauthorized: リフレッシュトークンが期限切れ、または更新に利用できない
                場合。
        """
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
        """セッションIDとCSRFトークンを検証し、Spoonのイベントストリームへ接続します。

        session_idはHMAC-SHA256でハッシュ化したうえでDBを検索します。DBに保存された
        CSRFトークンと``x_csrf_token``が一致した場合のみ、対象ユーザーの認可情報を使って
        EventStreamへの接続を開始します。

        通常、このメソッドをライブラリ利用者が利用することはありません。ストリームへの接続はライブラリによって管理されています。

        Args:
            session_id: クライアントが保持している生のセッションID。
            x_csrf_token: クライアントから送信されたCSRFトークン。

        Returns:
            bool: イベントストリームへの接続追加に成功した場合は``True``。

        Raises:
            HTTPUnauthorized: セッションが存在しない場合、またはリフレッシュトークンが
                期限切れの場合。
            HTTPForbidden: CSRFトークンが未設定、または送信値と一致しない場合。
        """
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
        """認可情報をトークン保存領域へ保存します。

        対象Spoonユーザーのトークンが既に存在する場合は更新し、存在しない場合は新規挿入します。
        ``force_refresh``に``True``を指定すると既存確認を行わず、常に更新処理を実行します。

        通常、このメソッドをライブラリ利用者が利用することはありません。セッションはライブラリによって管理されています。
        セッションを高度に制御したい場合のみ利用します。

        Args:
            authorization: 保存対象の認可情報。
            force_refresh: 既存トークンの有無にかかわらず更新するかどうか。
                デフォルトは``False``。

        Returns:
            bool: 保存（挿入または更新）に成功した場合は``True``、失敗した場合は
                ``False``。
        """
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
        """認可情報に紐づく新しいログインセッションを作成します。

        推測困難なセッションIDを生成し、DBにはHMAC-SHA256でハッシュ化した値のみを保存します。
        セッションの有効期限は``DEFAULT_SESSION_EXPIRES_IN``秒後です。

        通常、このメソッドをライブラリ利用者が利用することはありません。セッションはライブラリによって管理されています。
        セッションを高度に制御したい場合のみ利用します。

        Args:
            authorization: セッションを紐づける認可情報。

        Returns:
            str: クライアントへ返却する生のセッションID。DBには保存されないため、
            この値は発行時にのみ取得できます。

        Raises:
            HTTPInternalServerError: セッションのDB保存に失敗した場合。
        """
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

    async def get_authorization_by_session_id(
        self, session_id: str
    ) -> SpoonAuthorization:
        """セッションIDから対応する認可情報を取得します。

        受け取ったセッションIDをHMAC-SHA256でハッシュ化してセッションを検索し、
        紐づくSpoonユーザーのトークン情報を``SpoonAuthorization``として返します。

        Args:
            session_id: クライアントが保持している生のセッションID。

        Returns:
            SpoonAuthorization: セッションに紐づく認可情報。

        Raises:
            HTTPUnauthorized: セッションまたはトークン情報が存在しない場合。
        """
        session_data = await self.spoon_user_repository.get_session_data(
            self._hmac_sha256(session_id)
        )
        if session_data is None:
            raise HTTPUnauthorized()
        token_data = await self.spoon_user_repository.get_token_data(
            session_data.authorization_spoon_user_id
        )
        if token_data is None:
            raise HTTPUnauthorized()
        return SpoonAuthorization(
            id=token_data.id,
            access_token=token_data.access_token,
            token_type=token_data.token_type,
            expire_at=token_data.expire_at,
            refresh_expire_at=token_data.refresh_expire_at,
            refresh_token=token_data.refresh_token,
            scope=token_data.scope,
            token_status=TokenStatus(token_data.token_status),
        )

    async def regenerate_csrf_token(self, session_id: str) -> str:
        """セッションに紐づくCSRFトークンを再発行します。

        新しいランダムなCSRFトークンを生成してDBを更新します。EventStream接続時の
        検証にはこの値を使用します。

        通常、このメソッドをライブラリ利用者が利用することはありません。セッションはライブラリによって管理されています。
        セッションを高度に制御したい場合のみ利用します。

        Args:
            session_id: 対象セッションの生のID。

        Returns:
            str: 新しく発行されたCSRFトークン。

        Raises:
            HTTPInternalServerError: DB上のCSRFトークン更新に失敗した場合。
        """
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
