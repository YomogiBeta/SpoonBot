from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TypeVar

from spoonbot.db.dto import UpdateResult
from spoonbot.db.types import DBValueType

ResponseGenericType = TypeVar("ResponseGenericType")


class DatabaseClient(ABC):
    @abstractmethod
    def initialize(self, *args, **kwargs):
        pass

    @abstractmethod
    async def execute_one(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        pass

    @abstractmethod
    async def execute_many(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        pass

    @asynccontextmanager
    async def transaction(self):
        pass

    @abstractmethod
    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> UpdateResult:
        pass
