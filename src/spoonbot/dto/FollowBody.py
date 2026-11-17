from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class FollowBody(BaseModel, frozen=True):
    """Spoonのフォロー1件分の内容を保持するDTOです。

    ``FollowEvent``の``follow_body``として利用されます。

    Attributes:
        user: DJをフォローしたユーザー。
        time: フォローが行われた日時。
    """

    user: User
    time: datetime
