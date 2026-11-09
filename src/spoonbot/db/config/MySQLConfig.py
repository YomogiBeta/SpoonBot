from dataclasses import dataclass


@dataclass
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str = "spoon_bot"
    charset: str = "utf8mb4"
