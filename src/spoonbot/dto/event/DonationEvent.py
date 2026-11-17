from pydantic import BaseModel

from spoonbot.dto.DonationBody import DonationBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class GiftEvent(BaseModel, frozen=True):
    """リスナーがギフト（投げ銭）を送信したときに発行されるイベントです。

    ギフトの送信者、金額、メッセージなどを保持します。
    ``SpoonBot.gift_event``で登録したコールバックの引数として渡されます。

    Attributes:
        donation_body: 送信されたギフトの送信者、金額、メッセージ、送信時刻を
            保持するオブジェクト。
        authorization: ギフトを受信したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    donation_body: DonationBody
    authorization: SpoonAuthorization
