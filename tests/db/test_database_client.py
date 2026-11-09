import unittest
from unittest.mock import AsyncMock, patch

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DatabaseClient import DatabaseClient
from spoonbot.db.DBType import DBType


class CreateTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_without_config_creates_sqlite_client(self) -> None:
        with (
            patch(
                "spoonbot.db.sqlite3.Sqlite3Client.Sqlite3Client"
            ) as sqlite_client_cls,
            patch("spoonbot.db.mysql.MySQLClient.MySQLClient") as mysql_client_cls,
        ):
            sqlite_client = sqlite_client_cls.return_value
            sqlite_client.initialize = AsyncMock()

            result = await DatabaseClient.create()

        sqlite_client_cls.assert_called_once_with(DBType.SQLITE3)
        sqlite_client.initialize.assert_awaited_once_with()
        mysql_client_cls.assert_not_called()
        self.assertIs(result, sqlite_client)

    async def test_create_with_config_creates_mysql_client(self) -> None:
        config = MySQLConfig(
            host="db.example.com",
            user="spoon",
            password="secret",
            database="spoon_bot",
            charset="utf8mb4",
        )

        with (
            patch(
                "spoonbot.db.sqlite3.Sqlite3Client.Sqlite3Client"
            ) as sqlite_client_cls,
            patch("spoonbot.db.mysql.MySQLClient.MySQLClient") as mysql_client_cls,
        ):
            mysql_client = mysql_client_cls.return_value
            mysql_client.initialize = AsyncMock()

            result = await DatabaseClient.create(config)

        mysql_client_cls.assert_called_once_with(DBType.MYSQL)
        mysql_client.initialize.assert_awaited_once_with(config)
        sqlite_client_cls.assert_not_called()
        self.assertIs(result, mysql_client)

    async def test_create_propagates_initialize_error(self) -> None:
        error = RuntimeError("boom")

        with (
            patch(
                "spoonbot.db.sqlite3.Sqlite3Client.Sqlite3Client"
            ) as sqlite_client_cls,
            patch("spoonbot.db.mysql.MySQLClient.MySQLClient"),
        ):
            sqlite_client = sqlite_client_cls.return_value
            sqlite_client.initialize = AsyncMock(side_effect=error)

            with self.assertRaises(RuntimeError) as context:
                await DatabaseClient.create()

        self.assertIs(context.exception, error)
        sqlite_client.initialize.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
