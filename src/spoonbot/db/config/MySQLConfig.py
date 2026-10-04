from dataclasses import dataclass


@dataclass
class MySQLConfig:
    host: str
    user: str
    password: str
    database: str = "spoon_bot"
    charset: str = "utf8mb4"
