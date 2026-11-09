import re
import unittest
from typing import Self, cast
from unittest.mock import AsyncMock, patch

import aiomysql
from pydantic import BaseModel

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DBType import DBType
from spoonbot.db.mysql.MySQLClient import (
    POOL_MAX_SIZE,
    POOL_MIN_SIZE,
    MySQLClient,
    _current_connection,
)


class RowDto(BaseModel):
    id: int
    name: str


class FakeCursor:
    def __init__(
        self,
        fetchone_result: dict | None = None,
        fetchall_result: list[dict] | None = None,
        rowcount: int = 0,
    ) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result
        self.rowcount = rowcount
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, query: str, args: dict | None = None) -> None:
        self.executed.append((query, args or {}))

    async def fetchone(self) -> dict | None:
        return self.fetchone_result

    async def fetchall(self) -> list[dict] | None:
        return self.fetchall_result

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    async def begin(self) -> None:
        self.begin_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *exc_info) -> bool:
        return False


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.acquire_calls = 0
        self.close_calls = 0
        self.wait_closed_calls = 0

    def acquire(self) -> FakeAcquireContext:
        self.acquire_calls += 1
        return FakeAcquireContext(self._connection)

    def close(self) -> None:
        self.close_calls += 1

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


class MySQLClientTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = MySQLClient(DBType.MYSQL)
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)
        self.pool = FakePool(self.connection)
        self.client.pool = cast(aiomysql.Pool, self.pool)
        _current_connection.set(None)

    def tearDown(self) -> None:
        _current_connection.set(None)

    def set_transaction_connection(self) -> None:
        _current_connection.set(cast(aiomysql.Connection, self.connection))


class InitializeTest(MySQLClientTestBase):
    async def test_initialize_creates_pool_with_config(self) -> None:
        config = MySQLConfig(
            host="db.example.com",
            user="spoon",
            password="secret",
            database="spoon_bot",
            charset="utf8mb4",
        )

        with patch.object(
            aiomysql,
            "create_pool",
            new=AsyncMock(return_value=self.pool),
        ) as create_pool:
            client = MySQLClient(DBType.MYSQL)
            await client.initialize(config)

        self.assertIs(client.pool, self.pool)
        create_pool.assert_awaited_once_with(
            host="db.example.com",
            user="spoon",
            password="secret",
            database="spoon_bot",
            charset="utf8mb4",
            minsize=POOL_MIN_SIZE,
            maxsize=POOL_MAX_SIZE,
            autocommit=False,
            cursorclass=aiomysql.DictCursor,
        )


class CloseTest(MySQLClientTestBase):
    async def test_close_closes_pool_and_waits(self) -> None:
        await self.client.close()

        self.assertEqual(self.pool.close_calls, 1)
        self.assertEqual(self.pool.wait_closed_calls, 1)

    async def test_close_without_pool_does_nothing(self) -> None:
        client = MySQLClient(DBType.MYSQL)

        await client.close()


class PlaceholderTest(MySQLClientTestBase):
    def test_placeholder_returns_pyformat_placeholder(self) -> None:
        self.assertEqual(self.client.placeholder("id"), "%(id)s")


class ExecuteOneTest(MySQLClientTestBase):
    async def test_execute_one_returns_validated_model(self) -> None:
        self.cursor.fetchone_result = {"id": 1, "name": "spoon"}

        result = await self.client.execute_one(
            "SELECT id, name FROM users WHERE id = %(id)s",
            args={"id": 1},
            response_type=RowDto,
        )

        self.assertEqual(result, RowDto(id=1, name="spoon"))
        self.assertEqual(
            self.cursor.executed,
            [("SELECT id, name FROM users WHERE id = %(id)s", {"id": 1})],
        )
        self.assertEqual(self.pool.acquire_calls, 1)
        self.assertEqual(self.connection.rollback_calls, 1)

    async def test_execute_one_uses_empty_args_when_none(self) -> None:
        self.cursor.fetchone_result = {"id": 1, "name": "spoon"}

        await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertEqual(self.cursor.executed, [("SELECT 1", {})])

    async def test_execute_one_returns_none_when_no_row(self) -> None:
        self.cursor.fetchone_result = None

        result = await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertIsNone(result)

    async def test_execute_one_reuses_transaction_connection(self) -> None:
        self.cursor.fetchone_result = {"id": 1, "name": "spoon"}
        self.set_transaction_connection()

        result = await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertEqual(result, RowDto(id=1, name="spoon"))
        self.assertEqual(self.pool.acquire_calls, 0)
        self.assertEqual(self.connection.rollback_calls, 0)


class ExecuteManyTest(MySQLClientTestBase):
    async def test_execute_many_returns_validated_models(self) -> None:
        self.cursor.fetchall_result = [
            {"id": 1, "name": "spoon"},
            {"id": 2, "name": "fork"},
        ]

        result = await self.client.execute_many(
            "SELECT id, name FROM users",
            response_type=list[RowDto],
        )

        self.assertEqual(
            result,
            [RowDto(id=1, name="spoon"), RowDto(id=2, name="fork")],
        )
        self.assertEqual(self.pool.acquire_calls, 1)
        self.assertEqual(self.connection.rollback_calls, 1)

    async def test_execute_many_uses_empty_args_when_none(self) -> None:
        self.cursor.fetchall_result = []

        await self.client.execute_many("SELECT 1", response_type=list[RowDto])

        self.assertEqual(self.cursor.executed, [("SELECT 1", {})])

    async def test_execute_many_returns_none_when_fetchall_is_none(self) -> None:
        self.cursor.fetchall_result = None

        result = await self.client.execute_many("SELECT 1", response_type=list[RowDto])

        self.assertIsNone(result)

    async def test_execute_many_reuses_transaction_connection(self) -> None:
        self.cursor.fetchall_result = [{"id": 1, "name": "spoon"}]
        self.set_transaction_connection()

        result = await self.client.execute_many("SELECT 1", response_type=list[RowDto])

        self.assertEqual(result, [RowDto(id=1, name="spoon")])
        self.assertEqual(self.pool.acquire_calls, 0)
        self.assertEqual(self.connection.rollback_calls, 0)


class ExecuteCudTest(MySQLClientTestBase):
    async def test_execute_cud_commits_and_returns_rowcount(self) -> None:
        self.cursor.rowcount = 3

        result = await self.client.execute_cud(
            "UPDATE users SET name = %(name)s",
            args={"name": "spoon"},
        )

        self.assertEqual(result, 3)
        self.assertEqual(
            self.cursor.executed,
            [("UPDATE users SET name = %(name)s", {"name": "spoon"})],
        )
        self.assertEqual(self.connection.commit_calls, 1)

    async def test_execute_cud_uses_empty_args_when_none(self) -> None:
        await self.client.execute_cud("DELETE FROM users")

        self.assertEqual(self.cursor.executed, [("DELETE FROM users", {})])

    async def test_execute_cud_inside_transaction_does_not_commit(self) -> None:
        self.cursor.rowcount = 1
        self.set_transaction_connection()

        result = await self.client.execute_cud("DELETE FROM users")

        self.assertEqual(result, 1)
        self.assertEqual(self.pool.acquire_calls, 0)
        self.assertEqual(self.connection.commit_calls, 0)


class TransactionTest(MySQLClientTestBase):
    async def test_transaction_commits_and_resets_context(self) -> None:
        async with self.client.transaction() as connection:
            self.assertIs(connection, self.connection)
            self.assertIs(_current_connection.get(), self.connection)

        self.assertEqual(self.connection.begin_calls, 1)
        self.assertEqual(self.connection.commit_calls, 1)
        self.assertEqual(self.connection.rollback_calls, 0)
        self.assertIsNone(_current_connection.get())

    async def test_transaction_rolls_back_and_reraises_on_error(self) -> None:
        error = RuntimeError("boom")

        with self.assertRaises(RuntimeError) as context:
            async with self.client.transaction():
                raise error

        self.assertIs(context.exception, error)
        self.assertEqual(self.connection.begin_calls, 1)
        self.assertEqual(self.connection.commit_calls, 0)
        self.assertEqual(self.connection.rollback_calls, 1)
        self.assertIsNone(_current_connection.get())

    async def test_nested_transaction_uses_savepoint(self) -> None:
        self.set_transaction_connection()

        async with self.client.transaction() as connection:
            self.assertIs(connection, self.connection)

        self.assertEqual(self.pool.acquire_calls, 0)
        self.assertEqual(self.connection.begin_calls, 0)
        self.assertEqual(self.connection.commit_calls, 0)
        self.assertEqual(self.connection.rollback_calls, 0)

        queries = [query for query, _ in self.cursor.executed]
        self.assertEqual(len(queries), 2)
        savepoint_match = re.fullmatch(r"SAVEPOINT (sp_[0-9a-f]{32})", queries[0])
        assert savepoint_match is not None
        savepoint_name = savepoint_match.group(1)
        self.assertEqual(queries[1], f"RELEASE SAVEPOINT {savepoint_name}")

    async def test_nested_transaction_rolls_back_to_savepoint_on_error(
        self,
    ) -> None:
        self.set_transaction_connection()
        error = RuntimeError("boom")

        with self.assertRaises(RuntimeError) as context:
            async with self.client.transaction():
                raise error

        self.assertIs(context.exception, error)
        self.assertEqual(self.connection.rollback_calls, 0)
        self.assertEqual(self.connection.commit_calls, 0)

        queries = [query for query, _ in self.cursor.executed]
        self.assertEqual(len(queries), 2)
        savepoint_match = re.fullmatch(r"SAVEPOINT (sp_[0-9a-f]{32})", queries[0])
        assert savepoint_match is not None
        savepoint_name = savepoint_match.group(1)
        self.assertEqual(queries[1], f"ROLLBACK TO SAVEPOINT {savepoint_name}")


if __name__ == "__main__":
    unittest.main()
