from pydantic import BaseModel

from spoonbot.dto.PresenceBody import PresenceBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class JoinEvent(BaseModel, frozen=True):
    """リスナーがライブへ入室したときに発行されるイベントです。

    入室したユーザーと、入室が発生したライブルームの情報を保持します。
    ``SpoonBot.join_event``で登録したコールバックの引数として渡されます。

    Attributes:
        presence_body: 入室したユーザー、入室種別、ファンランク、
            マネージャーかどうか、お気に入り温度、入室時刻を保持するオブジェクト。
        authorization: 入室が発生したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    presence_body: PresenceBody
    authorization: SpoonAuthorization
