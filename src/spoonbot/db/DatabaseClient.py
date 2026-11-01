from abc import ABC, abstractmethod
from typing import LiteralString, TypeVar

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DBType import DBType
from spoonbot.db.types import DBValueType

ResponseGenericType = TypeVar("ResponseGenericType")


class DatabaseClient(ABC):
    db_type: DBType

    def __init__(self, db_type: DBType) -> None:
        self.db_type = db_type

    @classmethod
    async def create(cls, config: MySQLConfig | None = None) -> "DatabaseClient":
        # lazy import
        from spoonbot.db.mysql.MySQLClient import MySQLClient
        from spoonbot.db.sqlite3.Sqlite3Client import Sqlite3Client

        if config is None:
            client = Sqlite3Client(DBType.SQLITE3)
            await client.initialize()
            return client
        client = MySQLClient(DBType.MYSQL)
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
    ) -> ResponseGenericType | None:
        pass

    @abstractmethod
    async def execute_many(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType | None:
        pass

    @abstractmethod
    async def transaction(self):
        pass

    @abstractmethod
    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> int:
        pass

    @abstractmethod
    def placeholder(self, name: LiteralString) -> str:
        pass

    def get_db_type(self) -> DBType:
        return self.db_type
