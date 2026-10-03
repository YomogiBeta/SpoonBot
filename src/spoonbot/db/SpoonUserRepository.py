from spoonbot.db.DatabaseClient import DatabaseClient
from spoonbot.db.dto.MySQLConfig import MySQLConfig


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
