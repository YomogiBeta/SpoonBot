from typing import Iterable

from pydantic import BaseModel


class Subscription(BaseModel, frozen=True):
    """リスナーのサブスクリプション情報を保持するDTOです。

    Attributes:
        plan: 契約しているサブスクリプションプラン。
    """

    plan: str


class SpoonListener(BaseModel, frozen=True):
    """ライブルームに参加しているリスナー1人分の情報を保持するDTOです。

    Attributes:
        id: SpoonユーザーID。
        nickname: 表示名。
        subscription: サブスクリプション情報。未加入の場合は``None``。
    """

    id: str
    nickname: str
    subscription: Subscription | None


class ListenerData(BaseModel):
    """ライブルームに参加しているリスナーの一覧を保持するDTOです。

    ``SpoonBot.get_live_listeners``の戻り値として利用されます。

    Attributes:
        listeners: 取得したリスナーの一覧。初期値は空のリストです。
    """

    listeners: list[SpoonListener] = []

    def append(self, listener: SpoonListener):
        """リスナーを一覧の末尾に1人追加します。

        Args:
            listener: 追加するリスナー。
        """
        self.listeners.append(listener)

    def extend(self, listeners: Iterable[SpoonListener]):
        """複数のリスナーを一覧の末尾にまとめて追加します。

        Args:
            listeners: 追加するリスナーの反復可能オブジェクト。
        """
        self.extend(listeners)
