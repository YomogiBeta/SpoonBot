from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class DonationBody(BaseModel, frozen=True):
    """Spoonのギフト（投げ銭）1件分の内容を保持するDTOです。

    ``GiftEvent``の``donation_body``として利用されます。

    Attributes:
        user: ギフトを送信したユーザー。
        amount: ギフトの金額。
        message: ギフトに添えられたメッセージ。未設定の場合は``None``。
        time: ギフトが送信された日時。
    """

    user: User
    amount: int
    message: str | None
    time: datetime
