import asyncio

from aiohttp import ClientSession, web

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient


class SpoonEventStreamService:
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
        if task:
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


async def on_startup(app: web.Application):
    app["client_session"] = ClientSession()
    # マネージャーをインスタンス化して app に持たせる
    app["sse_manager"] = SpoonEventStreamService(app)

    # 起動直後にコードからメソッドを呼んで接続を追加する
    manager: SpoonEventStreamService = app["sse_manager"]
    await manager.add_connection("Stream-1", "https://httpbin.org/stream/5")

    # 少し遅らせて別の接続をメソッドで追加するシミュレーション
    asyncio.create_task(delayed_add(manager))


async def delayed_add(manager: SpoonEventStreamService):
    await asyncio.sleep(3.0)
    # メソッド呼び出しで新しいコネクションを追加
    await manager.add_connection("Stream-2", "https://httpbin.org/stream/5")


async def on_cleanup(app: web.Application):
    manager: SpoonEventStreamService = app["sse_manager"]
    for task in list(manager.tasks.values()):
        task.cancel()
    if manager.tasks:
        await asyncio.gather(*manager.tasks.values(), return_exceptions=True)
    await app["client_session"].close()


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(app, host="127.0.0.1", port=8080)
