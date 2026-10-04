import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import LiteralString

import aiomysql
from pydantic import TypeAdapter

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DatabaseClient import DatabaseClient, ResponseGenericType
from spoonbot.db.dto.UpdateResult import UpdateResult
from spoonbot.db.types import DBValueType

POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 10

_current_connection: ContextVar[aiomysql.Connection | None] = ContextVar(
    "_current_connection", default=None
)


class MySQLClient(DatabaseClient):
    pool: aiomysql.Pool

    async def initialize(
        self,
        config: MySQLConfig,
    ) -> None:
        self.pool = await aiomysql.create_pool(
            host=config.host,
            user=config.user,
            password=config.password,
            database=config.database,
            charset=config.charset,
            minsize=POOL_MIN_SIZE,
            maxsize=POOL_MAX_SIZE,
            autocommit=False,
            cursorclass=aiomysql.DictCursor,
        )

    async def close(self) -> None:
        if hasattr(self, "pool") and self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    @asynccontextmanager
    async def _get_connection(self):
        in_tx_conn = _current_connection.get()
        if in_tx_conn is not None:
            yield in_tx_conn
        else:
            connection: aiomysql.Connection
            async with self.pool.acquire() as connection:
                try:
                    yield connection
                finally:
                    await connection.rollback()

    async def execute_one(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}

        async with self._get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, args)
                result = await cursor.fetchone()
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(result)

    async def execute_many(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}

        async with self._get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, args)
                results = await cursor.fetchall()
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(results)

    @asynccontextmanager
    async def transaction(self):
        existing_conn = _current_connection.get()

        if existing_conn is not None:
            savepoint_name = f"sp_{uuid.uuid4().hex}"
            async with existing_conn.cursor() as cursor:
                await cursor.execute(f"SAVEPOINT {savepoint_name}")
            try:
                yield existing_conn
                async with existing_conn.cursor() as cursor:
                    await cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except Exception:
                async with existing_conn.cursor() as cursor:
                    await cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                raise
            return

        async with self.pool.acquire() as connection:
            await connection.begin()
            token = _current_connection.set(connection)
            try:
                yield connection
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
            finally:
                _current_connection.reset(token)

    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> UpdateResult:
        if args is None:
            args = {}

        in_tx_conn = _current_connection.get()

        if in_tx_conn is not None:
            async with in_tx_conn.cursor() as cursor:
                await cursor.execute(query, args)
                return UpdateResult(cursor.lastrowid, cursor.rowcount)
        else:
            async with self.pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query, args)
                    await connection.commit()
                    return UpdateResult(cursor.lastrowid, cursor.rowcount)

    def placeholder(self, name: LiteralString) -> str:
        return f"%({name})s"
