from pydantic import BaseModel


class RateLimit(BaseModel, frozen=True):
    """Spoon APIのレート制限情報を保持するDTOです。

    APIレスポンスのレート制限ヘッダーから生成され、
    ``BurstRequestException``や``DailyRequestLimitException``の
    ``token_ratelimit``として参照できます。

    Attributes:
        remaining: 現在のバースト制限における残りリクエスト数。
        replenish_rate: 単位時間あたりに回復するリクエスト数。
        burst_capacity: バースト時に許容されるリクエスト数の上限。
        daily_limit: 1日あたりのリクエスト上限。
        daily_remaining: 1日あたりの残りリクエスト数。
        daily_reset_epoch: 日次制限がリセットされる時刻（Unixエポック秒）。
        daily_limited_scope: 日次制限の対象スコープ。未設定の場合は``None``。
    """

    remaining: int
    replenish_rate: int
    burst_capacity: int
    daily_limit: int
    daily_remaining: int
    daily_reset_epoch: int
    daily_limited_scope: str | None
