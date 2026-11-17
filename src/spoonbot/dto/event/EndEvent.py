from pydantic import BaseModel

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class EndEvent(BaseModel, frozen=True):
    """ライブの配信が終了したときに発行されるイベントです。

    ``SpoonBot.end_event``で登録したコールバックの引数として渡されます。

    Attributes:
        authorization: 終了したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    authorization: SpoonAuthorization
