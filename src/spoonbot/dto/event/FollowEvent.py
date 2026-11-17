from pydantic import BaseModel

from spoonbot.dto.FollowBody import FollowBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class FollowEvent(BaseModel, frozen=True):
    """リスナーがDJをフォローしたときに発行されるイベントです。

    フォローしたユーザーと、フォローが発生したライブルームの情報を保持します。
    ``SpoonBot.follow_event``で登録したコールバックの引数として渡されます。

    Attributes:
        follow_body: フォローしたユーザーとフォロー時刻を保持するオブジェクト。
        authorization: フォローが発生したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    follow_body: FollowBody
    authorization: SpoonAuthorization
