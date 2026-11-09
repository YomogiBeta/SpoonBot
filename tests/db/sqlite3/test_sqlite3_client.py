import re
import unittest
from collections.abc import Generator
from typing import Any, Self, cast
from unittest.mock import patch

import aiosqlite
from pydantic import BaseModel

from spoonbot.db.DBType import DBType
from spoonbot.db.sqlite3.Sqlite3Client import Sqlite3Client, _current_sqlite_conn


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

    async def fetchone(self) -> dict | None:
        return self.fetchone_result

    async def fetchall(self) -> list[dict] | None:
        return self.fetchall_result

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    def __await__(self) -> Generator[Any, None, Self]:
        return self._identity().__await__()

    async def _identity(self) -> Self:
        return self


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.row_factory: object | None = None
        self.executed: list[tuple[str, dict]] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def execute(self, query: str, args: dict | None = None) -> FakeCursor:
        self.executed.append((query, args or {}))
        return self._cursor

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1

    async def close(self) -> None:
        self.close_calls += 1

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    def __await__(self) -> Generator[Any, None, Self]:
        return self._identity().__await__()

    async def _identity(self) -> Self:
        return self


class Sqlite3ClientTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = Sqlite3Client(DBType.SQLITE3)
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)
        self.client.connection = cast(aiosqlite.Connection, self.connection)
        self.tx_cursor = FakeCursor()
        self.tx_connection = FakeConnection(self.tx_cursor)
        _current_sqlite_conn.set(None)

    def tearDown(self) -> None:
        _current_sqlite_conn.set(None)

    def set_transaction_connection(self, connection: FakeConnection) -> None:
        _current_sqlite_conn.set(cast(aiosqlite.Connection, connection))


class InitializeTest(Sqlite3ClientTestBase):
    async def test_initialize_connects_and_sets_pragma(self) -> None:
        client = Sqlite3Client(DBType.SQLITE3)
        client.db_path = "test.db"

        with patch.object(
            aiosqlite,
            "connect",
            return_value=self.connection,
        ) as connect:
            await client.initialize()

        connect.assert_called_once_with("test.db", isolation_level=None)
        self.assertIs(client.connection.row_factory, aiosqlite.Row)
        self.assertEqual(
            self.connection.executed,
            [("PRAGMA journal_mode=WAL;", {})],
        )


class CloseTest(Sqlite3ClientTestBase):
    async def test_close_closes_connection(self) -> None:
        await self.client.close()

        self.assertEqual(self.connection.close_calls, 1)

    async def test_close_without_connection_does_nothing(self) -> None:
        client = Sqlite3Client(DBType.SQLITE3)

        await client.close()


class PlaceholderTest(Sqlite3ClientTestBase):
    def test_placeholder_returns_named_placeholder(self) -> None:
        self.assertEqual(self.client.placeholder("id"), ":id")


class GetConnectionTest(Sqlite3ClientTestBase):
    def test_get_connection_returns_default_connection(self) -> None:
        self.assertIs(self.client._get_connection(), self.connection)

    def test_get_connection_returns_transaction_connection(self) -> None:
        self.set_transaction_connection(self.tx_connection)

        self.assertIs(self.client._get_connection(), self.tx_connection)


class ExecuteOneTest(Sqlite3ClientTestBase):
    async def test_execute_one_returns_validated_model(self) -> None:
        self.cursor.fetchone_result = {"id": 1, "name": "spoon"}

        result = await self.client.execute_one(
            "SELECT id, name FROM users WHERE id = :id",
            args={"id": 1},
            response_type=RowDto,
        )

        self.assertEqual(result, RowDto(id=1, name="spoon"))
        self.assertEqual(
            self.connection.executed,
            [("SELECT id, name FROM users WHERE id = :id", {"id": 1})],
        )

    async def test_execute_one_uses_empty_args_when_none(self) -> None:
        self.cursor.fetchone_result = {"id": 1, "name": "spoon"}

        await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertEqual(self.connection.executed, [("SELECT 1", {})])

    async def test_execute_one_returns_none_when_no_row(self) -> None:
        self.cursor.fetchone_result = None

        result = await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertIsNone(result)

    async def test_execute_one_reuses_transaction_connection(self) -> None:
        self.tx_cursor.fetchone_result = {"id": 1, "name": "spoon"}
        self.set_transaction_connection(self.tx_connection)

        result = await self.client.execute_one("SELECT 1", response_type=RowDto)

        self.assertEqual(result, RowDto(id=1, name="spoon"))
        self.assertEqual(self.tx_connection.executed, [("SELECT 1", {})])
        self.assertEqual(self.connection.executed, [])


class ExecuteManyTest(Sqlite3ClientTestBase):
    async def test_execute_many_returns_validated_models(self) -> None:
        self.cursor.fetchall_result = [
            {"id": 1, "name": "spoon"},
            {"id": 2, "name": "fork"},
        ]

        result = await self.client.execute_many(
            "SELECT id, name FROM users",
            response_type=RowDto,
        )

        self.assertEqual(
            result,
            [RowDto(id=1, name="spoon"), RowDto(id=2, name="fork")],
        )
        self.assertEqual(
            self.connection.executed,
            [("SELECT id, name FROM users", {})],
        )

    async def test_execute_many_uses_empty_args_when_none(self) -> None:
        self.cursor.fetchall_result = []

        await self.client.execute_many("SELECT 1", response_type=RowDto)

        self.assertEqual(self.connection.executed, [("SELECT 1", {})])

    async def test_execute_many_returns_none_when_fetchall_is_none(self) -> None:
        self.cursor.fetchall_result = None

        result = await self.client.execute_many("SELECT 1", response_type=RowDto)

        self.assertIsNone(result)

    async def test_execute_many_reuses_transaction_connection(self) -> None:
        self.tx_cursor.fetchall_result = [{"id": 1, "name": "spoon"}]
        self.set_transaction_connection(self.tx_connection)

        result = await self.client.execute_many("SELECT 1", response_type=RowDto)

        self.assertEqual(result, [RowDto(id=1, name="spoon")])
        self.assertEqual(self.tx_connection.executed, [("SELECT 1", {})])
        self.assertEqual(self.connection.executed, [])


class ExecuteCudTest(Sqlite3ClientTestBase):
    async def test_execute_cud_returns_rowcount(self) -> None:
        self.cursor.rowcount = 3

        result = await self.client.execute_cud(
            "UPDATE users SET name = :name",
            args={"name": "spoon"},
        )

        self.assertEqual(result, 3)
        self.assertEqual(
            self.connection.executed,
            [("UPDATE users SET name = :name", {"name": "spoon"})],
        )
        self.assertEqual(self.connection.commit_calls, 0)

    async def test_execute_cud_uses_empty_args_when_none(self) -> None:
        await self.client.execute_cud("DELETE FROM users")

        self.assertEqual(self.connection.executed, [("DELETE FROM users", {})])

    async def test_execute_cud_reuses_transaction_connection(self) -> None:
        self.tx_cursor.rowcount = 1
        self.set_transaction_connection(self.tx_connection)

        result = await self.client.execute_cud("DELETE FROM users")

        self.assertEqual(result, 1)
        self.assertEqual(self.tx_connection.executed, [("DELETE FROM users", {})])
        self.assertEqual(self.connection.executed, [])


class TransactionTest(Sqlite3ClientTestBase):
    async def test_transaction_commits_and_resets_context(self) -> None:
        with patch.object(
            aiosqlite,
            "connect",
            return_value=self.connection,
        ) as connect:
            async with self.client.transaction() as connection:
                self.assertIs(connection, self.connection)
                self.assertIs(
                    _current_sqlite_conn.get(),
                    self.connection,
                )

        connect.assert_called_once_with(self.client.db_path, isolation_level=None)
        self.assertEqual(
            self.connection.executed,
            [("BEGIN TRANSACTION", {})],
        )
        self.assertEqual(self.connection.commit_calls, 1)
        self.assertEqual(self.connection.rollback_calls, 0)
        self.assertIsNone(_current_sqlite_conn.get())

    async def test_transaction_rolls_back_and_reraises_on_error(self) -> None:
        error = RuntimeError("boom")

        with (
            patch.object(
                aiosqlite,
                "connect",
                return_value=self.connection,
            ),
            self.assertRaises(RuntimeError) as context,
        ):
            async with self.client.transaction():
                raise error

        self.assertIs(context.exception, error)
        self.assertEqual(self.connection.executed, [("BEGIN TRANSACTION", {})])
        self.assertEqual(self.connection.commit_calls, 0)
        self.assertEqual(self.connection.rollback_calls, 1)
        self.assertIsNone(_current_sqlite_conn.get())

    async def test_nested_transaction_uses_savepoint(self) -> None:
        self.set_transaction_connection(self.tx_connection)

        with patch.object(
            aiosqlite,
            "connect",
            return_value=self.connection,
        ) as connect:
            async with self.client.transaction() as connection:
                self.assertIs(connection, self.tx_connection)

        connect.assert_not_called()
        self.assertEqual(self.connection.executed, [])
        self.assertEqual(self.tx_connection.commit_calls, 0)
        self.assertEqual(self.tx_connection.rollback_calls, 0)

        queries = [query for query, _ in self.tx_connection.executed]
        self.assertEqual(len(queries), 2)
        savepoint_match = re.fullmatch(r"SAVEPOINT (sp_[0-9a-f]{32})", queries[0])
        assert savepoint_match is not None
        savepoint_name = savepoint_match.group(1)
        self.assertEqual(queries[1], f"RELEASE SAVEPOINT {savepoint_name}")

    async def test_nested_transaction_rolls_back_to_savepoint_on_error(
        self,
    ) -> None:
        self.set_transaction_connection(self.tx_connection)
        error = RuntimeError("boom")

        with self.assertRaises(RuntimeError) as context:
            async with self.client.transaction():
                raise error

        self.assertIs(context.exception, error)
        self.assertEqual(self.connection.executed, [])
        self.assertEqual(self.tx_connection.commit_calls, 0)
        self.assertEqual(self.tx_connection.rollback_calls, 0)

        queries = [query for query, _ in self.tx_connection.executed]
        self.assertEqual(len(queries), 2)
        savepoint_match = re.fullmatch(r"SAVEPOINT (sp_[0-9a-f]{32})", queries[0])
        assert savepoint_match is not None
        savepoint_name = savepoint_match.group(1)
        self.assertEqual(queries[1], f"ROLLBACK TO SAVEPOINT {savepoint_name}")


if __name__ == "__main__":
    unittest.main()
