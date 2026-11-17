from datetime import datetime
from typing import Iterable

from pydantic import BaseModel

from spoonbot.dto.User import User


class Donation(BaseModel, frozen=True):
    """ライブルームで送信されたギフト（投げ銭）1件分を保持するDTOです。

    Attributes:
        user: ギフトを送信したユーザー。
        stickerName: ギフトに使用されたスタンプの名前。
        amount: ギフトの金額。
        time: ギフトが送信された日時。
    """

    user: User
    stickerName: str
    amount: int
    time: datetime


class DonationData(BaseModel):
    """ライブルームで送信されたギフト（投げ銭）の一覧を保持するDTOです。

    ``SpoonBot.get_live_donations``の戻り値として利用されます。

    Attributes:
        donations: 取得したギフトの一覧。初期値は空のリストです。
    """

    donations: list[Donation] = []

    def append(self, donation: Donation):
        """ギフトを一覧の末尾に1件追加します。

        Args:
            donation: 追加するギフト。
        """
        self.donations.append(donation)

    def extend(self, donations: Iterable[Donation]):
        """複数のギフトを一覧の末尾にまとめて追加します。

        Args:
            donations: 追加するギフトの反復可能オブジェクト。
        """
        self.extend(donations)
