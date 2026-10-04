from abc import ABC, abstractmethod
from typing import LiteralString, TypeVar

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.dto.UpdateResult import UpdateResult
from spoonbot.db.mysql.MySQLClient import MySQLClient
from spoonbot.db.sqlite3.Sqlite3Client import Sqlite3Client
from spoonbot.db.types import DBValueType

ResponseGenericType = TypeVar("ResponseGenericType")


class DatabaseClient(ABC):
    @classmethod
    async def create(cls, config: MySQLConfig | None = None) -> "DatabaseClient":
        if config is not None:
            client = Sqlite3Client()
            await client.initialize()
            return client
        assert config is not None
        client = MySQLClient()
        await client.initialize(config)
        return client

    @abstractmethod
    async def initialize(self, *args, **kwargs):
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def execute_one(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        pass

    @abstractmethod
    async def execute_many(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
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

    @abstractmethod
    def placeholder(self, name: LiteralString) -> str:
        pass
