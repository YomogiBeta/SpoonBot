import time

from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DatabaseClient import DatabaseClient
from spoonbot.db.dto.TokenDataDto import SessionDataDto, TokenDataDto


class SpoonUserRepository:
    database_client: DatabaseClient

    async def initialize(self, config: MySQLConfig | None = None):
        self.database_client = await DatabaseClient.create(config)
        await self._create_table()

    async def close(self):
        await self.database_client.close()

    async def _create_table(self):
        await self.database_client.execute_cud(
            query="""-- sql
              CREATE TABLE IF NOT EXISTS authorization_spoon_users (
                  id BINARY(16) PRIMARY KEY,
                  name VARCHAR(128) NOT NULL,
                  access_token VARCHAR(256) NOT NULL,
                  refresh_token VARCHAR(256) NOT NULL,
                  expire_at BIGINT,
                  refresh_expire_at BIGINT,
                  scope VARCHAR(128),
                  token_type VARCHAR(32),
                  token_status VARCHAR(32) DEFAULT "DEFAULT",
                  
                  created_at BIGINT NOT NULL, 
                  updated_at BIGINT NOT NULL,
                  
                  INDEX idx_expire_at (expire_at),
                  INDEX idx_expire_at (refresh_expire_at)
              )
            """
        )
        await self.database_client.execute_cud(
            query="""-- sql
              CREATE TABLE IF NOT EXISTS authorization_spoon_user_sessions (
                  id BINARY(16) PRIMARY KEY,
                  authorization_spoon_user_id BINARY(16) NOT NULL,
                  encoded_session_id BINARY(32) NOT NULL,
                  csrf_token BINARY(32),
                  
                  created_at BIGINT NOT NULL, 
                  updated_at BIGINT NOT NULL,
                  FOREIGN KEY (authorization_spoon_user_id) 
                      REFERENCES authorization_spoon_users(id),
                  INDEX idx_encoded_session_id (encoded_session_id),
                  INDEX idx_authorization_spoon_user_id (authorization_spoon_user_id)
              )
            """
        )

    async def insert_token(self, token: TokenDataDto) -> bool:
        epoch_seconds = int(time.time())
        result = await self.database_client.execute_cud(
            query=f"""-- sql
            INSERT INTO authorization_spoon_users (
                id,
                access_token,
                refresh_token,
                expire_at,
                refresh_expire_at,
                scope,
                token_type,
                created_at,
                updated_at
            ) VALUES (
                {self.database_client.placeholder("id")},
                {self.database_client.placeholder("access_token")},
                {self.database_client.placeholder("refresh_token")},
                {self.database_client.placeholder("expire_at")},
                {self.database_client.placeholder("refresh_expire_at")},
                {self.database_client.placeholder("scope")},
                {self.database_client.placeholder("token_type")},
                {self.database_client.placeholder("created_at")},
                {self.database_client.placeholder("updated_at")},
            )
            """,
            args=token.model_dump()
            | {"created_at": epoch_seconds, "updated_at": epoch_seconds},
        )
        return result.inserted_count == 1

    async def insert_session(self, session_data: SessionDataDto) -> bool:
        epoch_seconds = int(time.time())
        result = await self.database_client.execute_cud(
            query=f"""-- sql
            INSERT INTO authorization_spoon_user_sessions (
                id,
                authorization_spoon_user_id,
                encoded_session_id,
                csrf_token,
                created_at,
                updated_at
            ) VALUES (
                {self.database_client.placeholder("id")},
                {self.database_client.placeholder("authorization_spoon_user_id")},
                {self.database_client.placeholder("encoded_session_id")},
                {self.database_client.placeholder("csrf_token")},
                {self.database_client.placeholder("created_at")},
                {self.database_client.placeholder("updated_at")},
            )
            """,
            args=session_data.model_dump()
            | {"created_at": epoch_seconds, "updated_at": epoch_seconds},
        )
        return result.inserted_count == 1

    async def get_session_data(self, encoded_session_id: bytes) -> SessionDataDto:
        return await self.database_client.execute_one(
            query=f"""-- sql
            SELECT
                id,
                authorization_spoon_user_id,
                encoded_session_id,
                csrf_token
            FROM authorization_spoon_user_sessions
            WHERE encoded_session_id = {self.database_client.placeholder("encoded_session_id")}
            """,  # noqa: E501
            args={"encoded_session_id": encoded_session_id},
            response_type=SessionDataDto,
        )

    async def update_csrf_token(
        self, encoded_session_id: bytes, csrf_token: bytes
    ) -> bool:
        result = await self.database_client.execute_cud(
            query=f"""-- sql 
            UPDATE authorization_spoon_user_sessions
            SET csrf_token = {self.database_client.placeholder("csrf_token")}
            WHERE id = {self.database_client.placeholder("encoded_session_id")}
            LIMIt 1
            """,
            args={"encoded_session_id": encoded_session_id, "csrf_token": csrf_token},
        )
        return result.updated_count == 1
