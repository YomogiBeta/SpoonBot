import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar

import aiosqlite
from pydantic import TypeAdapter

from spoonbot.db.DatabaseClient import DatabaseClient, ResponseGenericType
from spoonbot.db.dto.UpdateResult import UpdateResult
from spoonbot.db.types import DBValueType

_current_sqlite_conn: ContextVar[aiosqlite.Connection | None] = ContextVar(
    "_current_sqlite_conn", default=None
)


class Sqlite3Client(DatabaseClient):
    connection: aiosqlite.Connection

    async def initialize(self):
        self.connection = aiosqlite.connect("spoonbot.db")
        async with self.connection as db:
            await db.execute("PRAGMA journal_mode=WAL;")

    def execute_one(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            result = cursor.fetchone()
            adapter = TypeAdapter(response_type)
            return adapter.validate_python(result)

    def execute_many(
        self,
        query: str,
        args: dict[DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType:
        if args is None:
            args = {}
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            results = cursor.fetchall()
            adapter = TypeAdapter(response_type)
            return adapter.validate_python(results)

    @asynccontextmanager
    async def transaction(self):
        existing_conn = _current_sqlite_conn.get()

        if existing_conn is not None:
            savepoint_name = f"sp_{id(asyncio.current_task())}"
            await existing_conn.execute(f"SAVEPOINT {savepoint_name}")
            try:
                yield existing_conn
                await existing_conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except Exception as exception:
                await existing_conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                raise exception  # noqa: TRY201
            return

        async with aiosqlite.connect(self.db_path, isolation_level=None) as connection:
            await connection.execute("BEGIN TRANSACTION")

            token = _current_sqlite_conn.set(connection)
            try:
                yield connection
                await connection.commit()
            except Exception as exception:
                await connection.rollback()
                raise exception  # noqa: TRY201
            finally:
                _current_sqlite_conn.reset(token)

    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> UpdateResult:
        if args is None:
            args = ()

        in_tx_conn = _current_sqlite_conn.get()

        if in_tx_conn is not None:
            async with in_tx_conn.execute(query, args) as cursor:
                return UpdateResult(cursor.lastrowid, cursor.rowcount)
        else:
            async with aiosqlite.connect(self.db_path) as connection:
                async with connection.execute(query, args) as cursor:
                    lastrowid, rowcount = cursor.lastrowid, cursor.rowcount
                await connection.commit()
                return UpdateResult(lastrowid, rowcount)
