from contextlib import asynccontextmanager
from contextvars import ContextVar

import aiomysql
from pydantic import TypeAdapter

from spoonbot.db.DatabaseClient import DatabaseClient, ResponseGenericType
from spoonbot.db.dto import UpdateResult
from spoonbot.db.dto.MySQLConfig import MySQLConfig
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
    ):
        self.pool = await aiomysql.create_pool(
            host=config.host,
            user=config.user,
            password=config.password,
            database=config.database,
            charset=config.charset,
            minsize=POOL_MIN_SIZE,
            maxsize=POOL_MAX_SIZE,
            autocommit=False,
        )

    async def execute_one(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}
        async with self.pool.acquire() as connection:
            connection: aiomysql.Connection
            async with connection.cursor() as cursor:
                cursor: aiomysql.Cursor
                cursor.execute(query, args)
                result = cursor.fetchone()
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(result)

    async def execute_many(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}
        async with self.pool.acquire() as connection:
            connection: aiomysql.Connection
            async with connection.cursor() as cursor:
                cursor: aiomysql.Cursor
                cursor.execute(query, args)
                result = cursor.fetchall()
                adapter = TypeAdapter(response_type)
                return adapter.validate_python(result)

    @asynccontextmanager
    async def transaction(self):
        existing_conn = _current_connection.get()
        if existing_conn is not None:
            yield existing_conn
            return

        async with self.pool.acquire() as connection:
            connection: aiomysql.Connection
            token = _current_connection.set(connection)
            try:
                yield connection
                await connection.commit()
            except Exception as exception:
                await connection.rollback()
                raise exception  # noqa: TRY201
            finally:
                _current_connection.reset(token)

    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> UpdateResult:
        if args is None:
            args = {}

        in_transaction_conn = _current_connection.get()

        if in_transaction_conn is not None:
            async with in_transaction_conn.cursor() as cursor:
                cursor: aiomysql.Cursor
                await cursor.execute(query, args)
                return UpdateResult(cursor.lastrowid, cursor.rowcount)
        else:
            async with self.pool.acquire() as connection:
                connection: aiomysql.Connection
                async with connection.cursor() as cursor:
                    cursor: aiomysql.Cursor
                    await cursor.execute(query, args)
                    await connection.commit()
                    return UpdateResult(cursor.lastrowid, cursor.rowcount)
