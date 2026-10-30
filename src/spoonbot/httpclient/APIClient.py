from abc import ABC
from typing import Any, Self, TypeVar

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from aiohttp_sse_client2 import client as sse_client
from pydantic import TypeAdapter

ResponseGenericType = TypeVar("ResponseGenericType")


class APIClient(ABC):
    _session: ClientSession
    _base_url: str

    def __init__(self, session: ClientSession, base_url: str):
        self._session = session
        self._base_url = base_url.rstrip("/") + "/"

    @classmethod
    async def create(cls, base_url: str) -> Self:
        connector = aiohttp.TCPConnector()
        session = aiohttp.ClientSession(base_url=base_url, connector=connector)
        return cls(session, base_url)

    async def close(self):
        await self._session.close()

    async def _get(
        self,
        endpoint: str,
        response_type: type[ResponseGenericType],
        queries: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> ResponseGenericType:
        async with self._session.get(
            endpoint, params=queries, headers=headers
        ) as response:
            response.raise_for_status()
            raw_json = await response.json()
            adapter = TypeAdapter(response_type)
            return adapter.validate_python(raw_json)

    async def _post(
        self,
        endpoint: str,
        body: Any,
        response_type: type[ResponseGenericType],
        headers: dict[str, str] | None = None,
    ) -> ResponseGenericType:
        async with self._session.post(endpoint, json=body, headers=headers) as response:
            response.raise_for_status()
            raw_json = await response.json()
            adapter = TypeAdapter(response_type)
            return adapter.validate_python(raw_json)

    async def _post_no_content(
        self,
        endpoint: str,
        body: Any,
        headers: dict[str, str] | None = None,
    ) -> bool:
        async with self._session.post(endpoint, json=body, headers=headers) as response:
            response.raise_for_status()
            return True

    def _sse_stream(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
    ):
        timeout = ClientTimeout(total=None)
        return sse_client.EventSource(
            f"{self._base_url}{endpoint}",
            session=self._session,
            headers=headers,
            timeout=timeout,
            raise_for_status=True,
        )
