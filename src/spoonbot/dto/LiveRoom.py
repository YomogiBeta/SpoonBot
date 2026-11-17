from datetime import datetime

from pydantic import BaseModel


class LiveRoom(BaseModel, frozen=True):
    """Spoonのライブルーム情報を保持するDTOです。

    ``SpoonBot.get_live``の戻り値として利用されます。

    Attributes:
        liveId: ライブのID。
        title: ライブのタイトル。
        startedAt: ライブの開始日時。
        closeAirTime: ライブの終了日時。
        listenerCount: 現在のリスナー数。
        totalListenerCount: 累計のリスナー数。
        welcomeMessage: ライブのウェルカムメッセージ。
        isChatFrozen: チャットが凍結されている場合は``True``。
        categories: ライブのカテゴリ一覧。
        tags: ライブのタグ一覧。
    """

    liveId: int
    title: str
    startedAt: datetime
    closeAirTime: datetime
    listenerCount: int
    totalListenerCount: int
    welcomeMessage: str
    isChatFrozen: bool
    categories: list[str]
    tags: list[str]
