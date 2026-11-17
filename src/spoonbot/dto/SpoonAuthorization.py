import time

from pydantic import BaseModel

from spoonbot.enums.TokenStatus import TokenStatus

TOKEN_EXPIRE_SECONDS_LEAST = 60 * 10
REFRESH_TOKEN_EXPIRE_SECONDS_LEAST = 60 * 60 * 24
END_REFRESH_TOKEN_SECONDS = 15


class SpoonAuthorization(BaseModel, frozen=True):
    """Spoon APIを利用するための認可情報を保持するDTOです。

    アクセストークンとリフレッシュトークン、それぞれの有効期限、スコープ、
    SpoonユーザーIDなどを保持します。イベントの``authorization``やAPI呼び出しの
    引数として利用されます。

    Attributes:
        id: SpoonユーザーID。ライブルームを識別するIDとしても利用されます。
        access_token: API呼び出しに使用するアクセストークン。
        token_type: トークンの種別（通常は``"Bearer"``）。
        expire_at: アクセストークンの有効期限（Unixエポック秒）。
        refresh_expire_at: リフレッシュトークンの有効期限（Unixエポック秒）。
        refresh_token: アクセストークンを更新するためのリフレッシュトークン。
        scope: 認可されたスコープ。
        token_status: トークンの状態。
    """

    id: str
    access_token: str
    token_type: str
    expire_at: int
    refresh_expire_at: int
    refresh_token: str
    scope: str
    token_status: TokenStatus

    def valid_access_token(self) -> bool:
        """アクセストークンが十分な余裕を持って有効かどうかを判定します。

        有効期限まで``TOKEN_EXPIRE_SECONDS_LEAST``秒（10分）より長い場合に
        ``True``を返します。API呼び出し直前に期限切れになるのを避けるための判定です。

        Returns:
            bool: アクセストークンがまだ利用可能と判断できる場合は``True``。
        """
        epoch_second = int(time.time())
        diff = self.expire_at - epoch_second
        return diff > TOKEN_EXPIRE_SECONDS_LEAST

    def valid_refresh_token(self) -> bool:
        """リフレッシュトークンが十分な余裕を持って有効かどうかを判定します。

        有効期限まで``REFRESH_TOKEN_EXPIRE_SECONDS_LEAST``秒（24時間）より長い場合に
        ``True``を返します。

        Returns:
            bool: リフレッシュトークンがまだ利用可能と判断できる場合は``True``。
        """
        epoch_second = int(time.time())
        diff = self.refresh_expire_at - epoch_second
        return diff > REFRESH_TOKEN_EXPIRE_SECONDS_LEAST

    def end_refresh_token(self) -> bool:
        """リフレッシュトークンが実質的に期限切れかどうかを判定します。

        有効期限まで``END_REFRESH_TOKEN_SECONDS``秒（15秒）以下の場合に``True``を
        返します。更新処理に間に合わなくなる直前に再認可が必要と判断するための判定です。

        Returns:
            bool: リフレッシュトークンが期限切れ間近の場合は``True``。
        """
        epoch_second = int(time.time())
        diff = self.refresh_expire_at - epoch_second
        return diff <= END_REFRESH_TOKEN_SECONDS
