from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from spoonbot.dto.User import User


class LikeType(StrEnum):
    """ライブの「いいね」種別を表す列挙型です。

    Attributes:
        PAID: 有料の「いいね」。
        FREE: 無料の「いいね」。
    """

    PAID = "PAID"
    FREE = "FREE"


class LikeBody(BaseModel, frozen=True):
    """Spoonの「いいね」1件分の内容を保持するDTOです。

    ``LikeEvent``の``like_body``として利用されます。

    Attributes:
        user: 「いいね」を送信したユーザー。
        type: 「いいね」の種別。
        totalAmount: ユーザーの累計「いいね」金額。
        amount: 今回送信された「いいね」の金額。
        extraAmount: 追加で送信された金額。
        combo: 連続して送信された回数（コンボ数）。未設定の場合は``None``。
        time: 「いいね」が送信された日時。
    """

    user: User
    type: LikeType
    totalAmount: int
    amount: int
    extraAmount: int
    combo: int | None
    time: datetime
