from pydantic import BaseModel


class RateLimit(BaseModel, frozen=True):
    remaining: int
    replenish_rate: int
    burst_capacity: int
    daily_limit: int
    daily_remaining: int
    daily_reset_epoch: int
    daily_limited_scope: str | None
