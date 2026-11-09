import unittest
from dataclasses import dataclass
from typing import LiteralString, cast
from unittest.mock import AsyncMock, patch

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DatabaseClient import DatabaseClient, ResponseGenericType
from spoonbot.db.DBType import DBType
from spoonbot.db.dto.TokenDataDto import SessionDataDto, TokenDataDto
from spoonbot.db.SpoonUserRepository import SpoonUserRepository
from spoonbot.db.types import DBValueType

FIXED_TIME = 1_700_000_000


def make_token(token_id: str = "user-1") -> TokenDataDto:
    return TokenDataDto(
        id=token_id,
        access_token="access-token",
        refresh_token="refresh-token",
        expire_at=2_000,
        refresh_expire_at=3_000,
        scope="scope",
        token_type="Bearer",
        token_status="DEFAULT",
    )


def make_session() -> SessionDataDto:
    return SessionDataDto(
        id=b"\x00" * 16,
        authorization_spoon_user_id="user-1",
        encoded_session_id=b"e" * 32,
        csrf_token=b"c" * 32,
        expires_at=4_000,
    )


@dataclass
class CudCall:
    query: str
    args: dict[str, DBValueType]


@dataclass
class OneCall:
    query: str
    args: dict[str, DBValueType]
    response_type: type | None


class FakeDatabaseClient:
    def __init__(
        self,
        db_type: DBType = DBType.MYSQL,
        cud_result: int = 1,
        one_result: object | None = None,
    ) -> None:
        self.db_type = db_type
        self.cud_result = cud_result
        self.one_result = one_result
        self.cud_calls: list[CudCall] = []
        self.one_calls: list[OneCall] = []
        self.close_calls = 0

    def get_db_type(self) -> DBType:
        return self.db_type

    def placeholder(self, name: LiteralString) -> str:
        if self.db_type == DBType.MYSQL:
            return f"%({name})s"
        return f":{name}"

    async def execute_cud(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
    ) -> int:
        self.cud_calls.append(CudCall(query=query, args=args or {}))
        return self.cud_result

    async def execute_one(
        self,
        query: str,
        args: dict[str, DBValueType] | None = None,
        response_type: type[ResponseGenericType] | None = None,
    ) -> object | None:
        self.one_calls.append(
            OneCall(query=query, args=args or {}, response_type=response_type)
        )
        return self.one_result

    async def close(self) -> None:
        self.close_calls += 1


class SpoonUserRepositoryTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.database_client = FakeDatabaseClient()
        self.repository = SpoonUserRepository()
        self.repository.database_client = cast(DatabaseClient, self.database_client)


class InitializeTest(SpoonUserRepositoryTestBase):
    async def test_initialize_creates_mysql_tables(self) -> None:
        config = MySQLConfig(
            host="db.example.com",
            port=3306,
            user="spoon",
            password="secret",
        )

        with patch(
            "spoonbot.db.SpoonUserRepository.DatabaseClient.create",
            new=AsyncMock(return_value=self.database_client),
        ) as create:
            await self.repository.initialize(config)

        create.assert_awaited_once_with(config)
        self.assertIs(self.repository.database_client, self.database_client)
        self.assertEqual(len(self.database_client.cud_calls), 2)

        queries = [call.query for call in self.database_client.cud_calls]
        self.assertIn("authorization_spoon_users", queries[0])
        self.assertIn("authorization_spoon_user_sessions", queries[1])

    async def test_initialize_without_config_creates_sqlite_tables(self) -> None:
        sqlite_client = FakeDatabaseClient(db_type=DBType.SQLITE3)

        with patch(
            "spoonbot.db.SpoonUserRepository.DatabaseClient.create",
            new=AsyncMock(return_value=sqlite_client),
        ) as create:
            await self.repository.initialize()

        create.assert_awaited_once_with(None)
        self.assertIs(self.repository.database_client, sqlite_client)
        self.assertEqual(len(sqlite_client.cud_calls), 6)

        queries = [call.query for call in sqlite_client.cud_calls]
        self.assertIn("authorization_spoon_users", queries[0])
        self.assertIn("idx_expire_at", queries[1])
        self.assertIn("idx_refresh_expire_at", queries[2])
        self.assertIn("authorization_spoon_user_sessions", queries[3])
        self.assertIn("idx_encoded_session_id", queries[4])
        self.assertIn("idx_authorization_spoon_user_id", queries[5])


class CloseTest(SpoonUserRepositoryTestBase):
    async def test_close_delegates_to_database_client(self) -> None:
        await self.repository.close()

        self.assertEqual(self.database_client.close_calls, 1)


class InsertTokenTest(SpoonUserRepositoryTestBase):
    async def test_insert_token_returns_true_on_success(self) -> None:
        token = make_token()

        with patch(
            "spoonbot.db.SpoonUserRepository.time.time", return_value=FIXED_TIME
        ):
            result = await self.repository.insert_token(token)

        self.assertTrue(result)
        self.assertEqual(len(self.database_client.cud_calls), 1)
        call = self.database_client.cud_calls[0]
        query = call.query
        self.assertIn("INSERT INTO authorization_spoon_users", query)
        self.assertIn("%(id)s", query)
        self.assertIn("%(access_token)s", query)
        self.assertEqual(
            call.args,
            token.model_dump() | {"created_at": FIXED_TIME, "updated_at": FIXED_TIME},
        )

    async def test_insert_token_returns_false_when_row_not_inserted(self) -> None:
        self.database_client.cud_result = 0

        result = await self.repository.insert_token(make_token())

        self.assertFalse(result)


class UpdateTokenTest(SpoonUserRepositoryTestBase):
    async def test_update_token_returns_true_on_success(self) -> None:
        token = make_token()

        with patch(
            "spoonbot.db.SpoonUserRepository.time.time", return_value=FIXED_TIME
        ):
            result = await self.repository.update_token(token)

        self.assertTrue(result)
        self.assertEqual(len(self.database_client.cud_calls), 1)
        call = self.database_client.cud_calls[0]
        query = call.query
        self.assertIn("UPDATE authorization_spoon_users", query)
        self.assertIn("WHERE id = %(id)s", query)
        self.assertEqual(
            call.args,
            token.model_dump() | {"updated_at": FIXED_TIME},
        )

    async def test_update_token_returns_false_when_row_not_updated(self) -> None:
        self.database_client.cud_result = 0

        result = await self.repository.update_token(make_token())

        self.assertFalse(result)


class GetTokenDataTest(SpoonUserRepositoryTestBase):
    async def test_get_token_data_passes_id_and_response_type(self) -> None:
        token = make_token()
        self.database_client.one_result = token

        result = await self.repository.get_token_data(token.id)

        self.assertIs(result, token)
        self.assertEqual(len(self.database_client.one_calls), 1)
        call = self.database_client.one_calls[0]
        query = call.query
        self.assertIn("FROM authorization_spoon_users", query)
        self.assertEqual(call.args, {"id": token.id})
        self.assertIs(call.response_type, TokenDataDto)


class GetTokenDataBySessionIdTest(SpoonUserRepositoryTestBase):
    async def test_get_token_data_by_session_id_passes_encoded_session_id(
        self,
    ) -> None:
        token = make_token()
        self.database_client.one_result = token
        encoded_session_id = b"e" * 32

        result = await self.repository.get_token_data_by_session_id(encoded_session_id)

        self.assertIs(result, token)
        self.assertEqual(len(self.database_client.one_calls), 1)
        call = self.database_client.one_calls[0]
        query = call.query
        self.assertIn("INNER JOIN authorization_spoon_user_sessions", query)
        self.assertEqual(call.args, {"encoded_session_id": encoded_session_id})
        self.assertIs(call.response_type, TokenDataDto)


class InsertSessionTest(SpoonUserRepositoryTestBase):
    async def test_insert_session_returns_true_on_success(self) -> None:
        session = make_session()

        with patch(
            "spoonbot.db.SpoonUserRepository.time.time", return_value=FIXED_TIME
        ):
            result = await self.repository.insert_session(session)

        self.assertTrue(result)
        self.assertEqual(len(self.database_client.cud_calls), 1)
        call = self.database_client.cud_calls[0]
        query = call.query
        self.assertIn("INSERT INTO authorization_spoon_user_sessions", query)
        self.assertEqual(
            call.args,
            session.model_dump() | {"created_at": FIXED_TIME, "updated_at": FIXED_TIME},
        )

    async def test_insert_session_returns_false_when_row_not_inserted(self) -> None:
        self.database_client.cud_result = 0

        result = await self.repository.insert_session(make_session())

        self.assertFalse(result)


class GetSessionDataTest(SpoonUserRepositoryTestBase):
    async def test_get_session_data_passes_encoded_session_id(self) -> None:
        session = make_session()
        self.database_client.one_result = session
        encoded_session_id = session.encoded_session_id

        result = await self.repository.get_session_data(encoded_session_id)

        self.assertIs(result, session)
        self.assertEqual(len(self.database_client.one_calls), 1)
        call = self.database_client.one_calls[0]
        query = call.query
        self.assertIn("FROM authorization_spoon_user_sessions", query)
        self.assertEqual(call.args, {"encoded_session_id": encoded_session_id})
        self.assertIs(call.response_type, SessionDataDto)


class UpdateCsrfTokenTest(SpoonUserRepositoryTestBase):
    async def test_update_csrf_token_returns_true_on_success(self) -> None:
        encoded_session_id = b"e" * 32
        csrf_token = b"n" * 32

        with patch(
            "spoonbot.db.SpoonUserRepository.time.time", return_value=FIXED_TIME
        ):
            result = await self.repository.update_csrf_token(
                encoded_session_id, csrf_token
            )

        self.assertTrue(result)
        self.assertEqual(len(self.database_client.cud_calls), 1)
        call = self.database_client.cud_calls[0]
        query = call.query
        self.assertIn("UPDATE authorization_spoon_user_sessions", query)
        self.assertIn("SET csrf_token = %(csrf_token)s", query)
        self.assertEqual(
            call.args,
            {
                "encoded_session_id": encoded_session_id,
                "csrf_token": csrf_token,
                "updated_at": FIXED_TIME,
            },
        )

    async def test_update_csrf_token_returns_false_when_row_not_updated(
        self,
    ) -> None:
        self.database_client.cud_result = 0

        result = await self.repository.update_csrf_token(b"e" * 32, b"n" * 32)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
