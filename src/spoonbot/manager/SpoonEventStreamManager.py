import asyncio
import json
import random
from typing import Any

from aiohttp import ClientConnectionError, ClientPayloadError, ClientResponseError, web

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.exception.BackoffRetryException import BackoffRetryException
from spoonbot.exception.NonBackoffRetryException import NonBackoffRetryException
from spoonbot.exception.NonRetryException import NonRetryException
from spoonbot.exception.TokenRefreshException import TokenRefreshException
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient
from spoonbot.spoon_bot import SpoonBot

DEFAULT_MAX_RETRIES = 6
MAX_DELAY = 30
# https://developers.spooncast.net/docs/en/api-reference/live-events#errors
BACKOFF_TARGET_HTTP_STATUS = 404, 502


class SpoonEventStreamManager:
    api_client: SpoonApiClient
    spoon_bot: SpoonBot

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

    async def _stream(self, authorization: SpoonAuthorization):
        async with self.api_client.stream_live(authorization) as event_source:
            async for event in event_source:
                payload = json.loads(event.data)
                if not isinstance(payload, dict):
                    pass
                payload: dict[str, Any]
                match event.type:
                    case "end":
                        await self.end_process(payload)

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

        try:
            for attempt in range(DEFAULT_MAX_RETRIES + 1):
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
                    if exception.status in BACKOFF_TARGET_HTTP_STATUS:
                        await wait_backoff(attempt)
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
                except BackoffRetryException as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                    await wait_backoff(attempt)
                except NonBackoffRetryException as exception:
                    if attempt == DEFAULT_MAX_RETRIES:
                        raise exception
                except NonRetryException:
                    raise
        finally:
            self.tasks.pop(authorization.id, None)
