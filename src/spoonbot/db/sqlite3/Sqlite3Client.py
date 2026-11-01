import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import LiteralString

import aiosqlite
from pydantic import TypeAdapter

from spoonbot.db.DatabaseClient import DatabaseClient, ResponseGenericType
from spoonbot.db.types import DBValueType

_current_sqlite_conn: ContextVar[aiosqlite.Connection | None] = ContextVar(
    "_current_sqlite_conn", default=None
)


class Sqlite3Client(DatabaseClient):
    connection: aiosqlite.Connection
    db_path: str = "spoonbot.db"

    async def initialize(self) -> None:
        self.connection = await aiosqlite.connect(self.db_path, isolation_level=None)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL;")

    async def close(self) -> None:
        if hasattr(self, "connection") and self.connection:
            await self.connection.close()

    def _get_connection(self) -> aiosqlite.Connection:
        in_tx_conn = _current_sqlite_conn.get()
        if in_tx_conn is not None:
            return in_tx_conn
        return self.connection

    async def execute_one(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> ResponseGenericType | None:
        if args is None:
            args = {}

        conn = self._get_connection()
        async with conn.execute(query, args) as cursor:
            result = await cursor.fetchone()
            if result is None:
                return None
            adapter = TypeAdapter(response_type)
            return adapter.validate_python(dict(result))

    async def execute_many(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> list[ResponseGenericType] | None:
        if args is None:
            args = {}

        conn = self._get_connection()
        async with conn.execute(query, args) as cursor:
            results = await cursor.fetchall()
            if results is None:
                return None
            adapter = TypeAdapter(response_type)
            return [adapter.validate_python(dict(row)) for row in results]

    @asynccontextmanager
    async def transaction(self):
        existing_conn = _current_sqlite_conn.get()

        if existing_conn is not None:
            savepoint_name = f"sp_{uuid.uuid4().hex}"
            await existing_conn.execute(f"SAVEPOINT {savepoint_name}")
            try:
                yield existing_conn
                await existing_conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except Exception:
                await existing_conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                raise
            return

        async with aiosqlite.connect(self.db_path, isolation_level=None) as connection:
            await connection.execute("BEGIN TRANSACTION")

            token = _current_sqlite_conn.set(connection)
            try:
                yield connection
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
            finally:
                _current_sqlite_conn.reset(token)

    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> int:
        if args is None:
            args = {}

        conn = self._get_connection()
        async with conn.execute(query, args) as cursor:
            return cursor.rowcount

    def placeholder(self, name: LiteralString) -> str:
        return f":{name}"
