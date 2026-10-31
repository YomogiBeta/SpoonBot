import asyncio
import json
import logging
import random
import time
from http import HTTPStatus
from importlib.metadata.diagnose import inspect
from typing import Any

from aiohttp import ClientConnectionError, ClientPayloadError, ClientResponseError, web

from spoonbot.dto.ChatBody import ChatBody
from spoonbot.dto.DonationBody import DonationBody
from spoonbot.dto.event.ChatEvent import ChatEvent
from spoonbot.dto.event.DonationEvent import GiftEvent
from spoonbot.dto.event.EndEvent import EndEvent
from spoonbot.dto.event.FollowEvent import FollowEvent
from spoonbot.dto.event.JoinEvent import JoinEvent
from spoonbot.dto.event.LikeEvent import LikeEvent
from spoonbot.dto.FollowBody import FollowBody
from spoonbot.dto.LikeBody import LikeBody
from spoonbot.dto.PresenceBody import PresenceBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.exception.BackoffRetryException import BackoffRetryException
from spoonbot.exception.NonBackoffRetryException import NonBackoffRetryException
from spoonbot.exception.NonRetryException import NonRetryException
from spoonbot.exception.TokenRefreshException import TokenRefreshException
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient
from spoonbot.spoon_bot import SpoonBot
from spoonbot.types.callback_types import (
    ChatFuncType,
    DonationFuncType,
    EndFuncType,
    FollowFuncType,
    LikeFuncType,
    PresenceFuncType,
)

DEFAULT_MAX_RETRIES = 6
MAX_DELAY = 30
BACKOFF_RESET_SECONDS = 60 * 3
MAX_LOOP = 300
# https://developers.spooncast.net/docs/en/api-reference/live-events#errors
BACKOFF_TARGET_HTTP_STATUS = 404, 500, 502
logger = logging.getLogger(__name__)


class SpoonEventStreamManager:
    api_client: SpoonApiClient
    spoon_bot: SpoonBot
    chat_callbacks: list[ChatFuncType]
    presence_callbacks: list[PresenceFuncType]
    like_callbacks: list[LikeFuncType]
    donation_callbacks: list[DonationFuncType]
    follow_callbacks: list[FollowFuncType]
    end_callbacks: list[EndFuncType]

    def __init__(
        self, app: web.Application, api_client: SpoonApiClient, spoon_bot: SpoonBot
    ):
        self.app = app
        self.api_client = api_client
        self.spoon_bot = spoon_bot
        self.tasks: dict[str, asyncio.Task] = {}

    async def add_connection(self, authorization: SpoonAuthorization):
        if authorization.id in self.tasks:
            return

        task = asyncio.create_task(self._do_task(authorization))
        self.tasks[authorization.id] = task

    async def remove_connection(self, client_id: str):
        task = self.tasks.get(client_id)
        if task is not None:
            task.cancel()

    def chat_callback_append(self, callback: ChatFuncType):
        self.chat_callbacks.append(callback)

    def presence_callback_append(self, callback: PresenceFuncType):
        self.presence_callbacks.append(callback)

    def like_callback_append(self, callback: LikeFuncType):
        self.like_callbacks.append(callback)

    def donation_callback_append(self, callback: DonationFuncType):
        self.donation_callbacks.append(callback)

    def follow_callback_append(self, callback: FollowFuncType):
        self.follow_callbacks.append(callback)

    def end_callback_append(self, callback: EndFuncType):
        self.end_callbacks.append(callback)

    async def _stream(self, authorization: SpoonAuthorization):
        async with self.api_client.stream_live(authorization) as event_source:
            async for event in event_source:
                payload = json.loads(event.data)
                if not isinstance(payload, dict):
                    pass
                payload: dict[str, Any]
                try:
                    match event.type.lower():
                        case "chat":
                            await self.chat_process(payload, authorization)
                        case "presence":
                            await self.presence_process(payload, authorization)
                        case "like":
                            await self.like_process(payload, authorization)
                        case "donation":
                            await self.donation_process(payload, authorization)
                        case "follow":
                            await self.follow_process(payload, authorization)
                        case "end":
                            await self.end_process(payload)
                except ClientResponseError as exception:
                    if exception.status == HTTPStatus.FORBIDDEN.value:
                        logger.warning(f"{exception.message}")
                        continue
                    raise exception

    async def chat_process(
        self, payload: dict[str, Any], authorization: SpoonAuthorization
    ):
        chat_body = ChatBody.model_validate(payload)
        chat_event = ChatEvent(chat_body=chat_body, authorization=authorization)
        for callback in self.chat_callbacks:
            result = callback(chat_event)
            if result is not None and inspect.isawaitable(result):
                await result

    async def presence_process(
        self, payload: dict[str, Any], authorization: SpoonAuthorization
    ):
        presence_body = PresenceBody.model_validate(payload)
        presence_event = JoinEvent(
            presence_body=presence_body, authorization=authorization
        )
        for callback in self.presence_callbacks:
            result = callback(presence_event)
            if result is not None and inspect.isawaitable(result):
                await result

    async def like_process(
        self, payload: dict[str, Any], authorization: SpoonAuthorization
    ):
        like_body = LikeBody.model_validate(payload)
        like_event = LikeEvent(like_body=like_body, authorization=authorization)
        for callback in self.like_callbacks:
            result = callback(like_event)
            if result is not None and inspect.isawaitable(result):
                await result

    async def donation_process(
        self, payload: dict[str, Any], authorization: SpoonAuthorization
    ):
        donation_body = DonationBody.model_validate(payload)
        donation_event = GiftEvent(
            donation_body=donation_body, authorization=authorization
        )
        for callback in self.donation_callbacks:
            result = callback(donation_event)
            if result is not None and inspect.isawaitable(result):
                await result

    async def follow_process(
        self, payload: dict[str, Any], authorization: SpoonAuthorization
    ):
        follow_body = FollowBody.model_validate(payload)
        follow_event = FollowEvent(follow_body=follow_body, authorization=authorization)
        for callback in self.follow_callbacks:
            result = callback(follow_event)
            if result is not None and inspect.isawaitable(result):
                await result

    async def end_process(self, payload: dict[str, Any]):
        reason = payload.get("reason")
        if not isinstance(reason, str):
            pass
        match reason:
            case "TOKEN_EXPIRED":
                raise TokenRefreshException()
            case "LIVE_ENDED" | "DUPLICATE_CONNECTION":
                raise NonRetryException()
            case "RECONNECT":
                raise NonBackoffRetryException()

    async def _refresh_token(
        self, authorization: SpoonAuthorization
    ) -> SpoonAuthorization:
        refresh_authorization = await self.spoon_bot.get_authorization_by_refresh_token(
            authorization
        )
        await self.spoon_bot.save_authorization(refresh_authorization, True)
        return refresh_authorization

    async def _do_task(self, authorization: SpoonAuthorization):
        async def wait_backoff(attempt: int):
            delay = min(2**attempt, MAX_DELAY)
            jitter = random.uniform(0, delay * 0.25)  # 25% Jitter
            await asyncio.sleep(delay + jitter)

        attempt = 0
        safety_index = 0
        backoff_anchor = None
        try:
            while attempt < DEFAULT_MAX_RETRIES and safety_index < MAX_LOOP:
                safety_index += 1
                if backoff_anchor is not None:
                    now = int(time.time())
                    if now - backoff_anchor >= BACKOFF_RESET_SECONDS:
                        attempt = 0
                        backoff_anchor = None
                try:
                    if (
                        not authorization.valid_refresh_token()
                        or not authorization.valid_access_token()
                    ):
                        authorization = await self._refresh_token(authorization)
                    await self._stream(authorization)
                except TokenRefreshException:
                    authorization = await self._refresh_token(authorization)
                except ClientResponseError as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                    if exception.status == HTTPStatus.UNAUTHORIZED.value:
                        authorization = await self._refresh_token(authorization)
                    if exception.status in BACKOFF_TARGET_HTTP_STATUS:
                        await wait_backoff(attempt)
                        attempt += 1
                        backoff_anchor = int(time.time())
                    else:
                        raise exception
                except (
                    ClientConnectionError,
                    ClientPayloadError,
                    asyncio.TimeoutError,
                ) as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                    await wait_backoff(attempt)
                    attempt += 1
                    backoff_anchor = int(time.time())
                except BackoffRetryException as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                    await wait_backoff(attempt)
                    attempt += 1
                    backoff_anchor = int(time.time())
                except NonBackoffRetryException as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                    continue
                except NonRetryException as exception:
                    raise exception
        except Exception as exception:
            logger.exception(
                "The stream connection was stopped due to an error: %s", exception
            )
        finally:
            for callback in self.end_callbacks:
                result = callback(EndEvent(authorization=authorization))
                if result is not None and inspect.isawaitable(result):
                    await result
            if safety_index >= MAX_LOOP:
                logger.error(
                    "The stream was stopped due to an unusually high number of Stream Loops."  # noqa: E501
                )
            self.tasks.pop(authorization.id, None)
