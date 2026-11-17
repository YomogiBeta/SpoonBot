from datetime import datetime

from pydantic import BaseModel

from spoonbot.dto.User import User


class ChatBody(BaseModel, frozen=True):
    """Spoonのチャット1件分の内容を保持するDTOです。

    ``ChatEvent``の``chat_body``として利用されます。

    Attributes:
        user: チャットを送信したユーザー。
        isDj: 送信者がDJの場合は``True``、それ以外は``False``。
        message: チャットの本文。
        sentTime: チャットが送信された日時。
    """

    user: User
    isDj: bool
    message: str
    sentTime: datetime
