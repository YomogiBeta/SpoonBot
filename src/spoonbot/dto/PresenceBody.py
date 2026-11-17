from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from spoonbot.dto.User import User


class PresenceType(StrEnum):
    """ライブへの入室イベントの種別を表す列挙型です。"""

    JOIN = "JOIN"


class PresenceBody(BaseModel, frozen=True):
    """Spoonのライブルーム入室1件分の内容を保持するDTOです。

    ``JoinEvent``の``presence_body``として利用されます。

    Attributes:
        user: ライブへ入室したユーザー。
        type: 入室イベントの種別。
        fanRank: ユーザーのファンランク。未設定の場合は``None``。
        isManager: ユーザーがマネージャーの場合は``True``。
        favoriteTemperature: ユーザーのお気に入り温度。未設定の場合は``None``。
        time: 入室が行われた日時。
    """

    user: User
    type: PresenceType
    fanRank: int | None
    isManager: bool
    favoriteTemperature: float | None
    time: datetime
