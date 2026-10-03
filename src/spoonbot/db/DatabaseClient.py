from abc import ABC, abstractmethod
from typing import Self, TypeVar

from spoonbot.db.dto import UpdateResult
from spoonbot.db.dto.MySQLConfig import MySQLConfig
from spoonbot.db.mysql.MySQLClient import MySQLClient
from spoonbot.db.sqlite3.Sqlite3Client import Sqlite3Client
from spoonbot.db.types import DBValueType

ResponseGenericType = TypeVar("ResponseGenericType")


class DatabaseClient(ABC):
    @classmethod
    async def create(cls, config: MySQLConfig | None = None) -> Self:
        if config is not None:
            client = Sqlite3Client()
            await client.initialize()
            return client
        client = MySQLClient()
        await client.initialize(config)
        return client

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

    @abstractmethod
    async def transaction(self):
        pass

    @abstractmethod
    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> UpdateResult:
        pass
