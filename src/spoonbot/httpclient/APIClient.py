


from abc import ABC
from typing import Any, Self, Type, TypeVar
import aiohttp
from aiohttp import ClientSession
from pydantic import TypeAdapter, ValidationError


ResponseGenericType = TypeVar("ResponseGenericType")


class APIClient(ABC):
    def __init__(self, session: ClientSession):
        self._session = session

    @classmethod
    async def create(cls, base_url: str) -> Self:
        connector = aiohttp.TCPConnector()
        session = aiohttp.ClientSession(base_url=base_url, connector=connector)
        return cls(session)
    
    async def get(self, endpoint: str, queries: dict[str, Any], response_type: Type[ResponseGenericType]) -> ResponseGenericType:
        async with self._session.get(endpoint, params=queries) as response:
            response.raise_for_status()
            raw_json = await response.json()
            try:
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(raw_json)
            except ValidationError as exception:
                raise exception
    
    async def post(self, endpoint: str, body: Any, response_type: Type[ResponseGenericType]) -> ResponseGenericType:
        async with self._session.post(endpoint, json=body) as response:
            response.raise_for_status()
            raw_json = await response.json()
            try:
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(raw_json)
            except ValidationError as exception:
                raise exception