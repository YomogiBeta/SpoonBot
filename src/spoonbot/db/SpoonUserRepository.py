from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.DatabaseClient import DatabaseClient
from spoonbot.db.dto.TokenDataDto import TokenDataDto


class SpoonUserRepository:
    database_client: DatabaseClient

    async def initialize(self, config: MySQLConfig | None = None):
        self.database_client = await DatabaseClient.create(config)
        await self._create_table()

    async def _create_table(self):
        await self.database_client.execute_cud(
            query="""-- sql
              CREATE TABLE IF NOT EXISTS authorization_spoon_users (
                  id BINARY(16) PRIMARY KEY,
                  access_token VARCHAR(256) NOT NULL,
                  refresh_token VARCHAR(256) NOT NULL,
                  expires_in BIGINT,
                  scope VARCHAR(128),
                  token_type VARCHAR(32),
                  
                  INDEX idx_expires_in (expires_in)
              )
            """
        )

    async def insert_token(self, token: TokenDataDto) -> bool:
        result = await self.database_client.execute_cud(
            query=f"""-- sql
            INSERT INTO authorization_spoon_users (
                id, access_token, refresh_token, expires_in, scope, token_type
            ) VALUES (
                {self.database_client.placeholder("id")},
                {self.database_client.placeholder("access_token")},
                {self.database_client.placeholder("refresh_token")},
                {self.database_client.placeholder("expires_in")},
                {self.database_client.placeholder("scope")},
                {self.database_client.placeholder("token_type")},
            )
            """,
            args=token.model_dump(),
        )
        return result.inserted_count == 1
