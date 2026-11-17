from pydantic import BaseModel

from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class ConnectEvent(BaseModel, frozen=True):
    """イベントストリームへの接続が確立したときに発行されるイベントです。

    初回接続と再接続を``reconnect``で判別できます。
    ``SpoonBot.connect_event``で登録したコールバックの引数として渡されます。

    Attributes:
        authorization: 接続先ライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
        reconnect: 再接続の場合は``True``、初回接続の場合は``False``。
    """

    authorization: SpoonAuthorization
    reconnect: bool = False
