from pydantic import BaseModel

from spoonbot.dto.LikeBody import LikeBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class LikeEvent(BaseModel, frozen=True):
    """リスナーが「いいね」を送信したときに発行されるイベントです。

    「いいね」を行ったユーザーと、送信されたライブルームの情報を保持します。
    ``SpoonBot.like_event``で登録したコールバックの引数として渡されます。

    Attributes:
        like_body: 「いいね」を行ったユーザー、種別、累計金額、今回の金額、
            追加金額、コンボ数、送信時刻を保持するオブジェクト。
        authorization: 「いいね」が発生したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    like_body: LikeBody
    authorization: SpoonAuthorization
