from pydantic import BaseModel


class User(BaseModel, frozen=True):
    """Spoonのユーザー情報を保持するDTOです。

    Attributes:
        id: SpoonユーザーID。
        nickname: 表示名。未設定の場合は``None``。
    """

    id: str
    nickname: str | None
