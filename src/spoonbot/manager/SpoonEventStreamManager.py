import asyncio

from aiohttp import web

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient


class SpoonEventStreamManager:
    api_client: SpoonApiClient

    def __init__(self, app: web.Application, api_client: SpoonApiClient):
        self.app = app
        self.api_client = api_client
        self.tasks: dict[str, asyncio.Task] = {}

    async def add_connection(self, authorization: SpoonAuthorization):
        if authorization.id.hex in self.tasks:
            return

        task = asyncio.create_task(self._stream(authorization))
        self.tasks[authorization.id.hex] = task

    async def remove_connection(self, client_id: str):
        task = self.tasks.get(client_id)
        if task is not None:
            task.cancel()

    async def _stream(self, authorization: SpoonAuthorization):
        try:
            async with self.api_client.stream_live(authorization) as event_source:
                async for event in event_source:
                    print(f"Received event: {event.data}")
        except asyncio.CancelledError:
            print(f"[{authorization.id.hex}] 接続がキャンセルされました。")
        except Exception as e:
            print(f"[{authorization.id.hex}] エラー: {e}")
        finally:
            self.tasks.pop(authorization.id.hex, None)
