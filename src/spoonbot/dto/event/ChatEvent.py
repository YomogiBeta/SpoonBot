from pydantic import BaseModel

from spoonbot.dto.ChatBody import ChatBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class ChatEvent(BaseModel, frozen=True):
    """ライブのチャットを受信したときに発行されるイベントです。

    チャットの内容と、受信したライブルームの認可情報を保持します。
    ``SpoonBot.chat_event``で登録したコールバックの引数として渡されます。

    Attributes:
        chat_body: 受信したチャットの本文、送信者、DJによる投稿かどうか、
            送信時刻を保持するオブジェクト。
        authorization: チャットを受信したライブルームの認可情報。
            ``authorization.id``はライブルームごとに固有のIDです。
    """

    chat_body: ChatBody
    authorization: SpoonAuthorization
