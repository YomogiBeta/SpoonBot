from pydantic import BaseModel


class Fan(BaseModel, frozen=True):
    """ライブルームのファン1人分の情報を保持するDTOです。

    Attributes:
        id: SpoonユーザーID。
        nickname: 表示名。
        rank: ファンランク。
        spoonCount: ユーザーが保有するSpoon数。未設定の場合は``None``。
    """

    id: str
    nickname: str
    rank: int
    spoonCount: int | None


class FanData(BaseModel, frozen=True):
    """ライブルームのファン情報を保持するDTOです。

    ``SpoonBot.get_live_fans``の戻り値として利用されます。

    Attributes:
        fans: ファンの一覧。
        totalCount: ファンの総数。
    """

    fans: list[Fan]
    totalCount: int
