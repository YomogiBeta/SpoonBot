from spoonbot.dto.RateLimit import RateLimit


class BurstRequestException(Exception):
    token_ratelimit: RateLimit

    def __init__(self, token_ratelimit: RateLimit, url: str):
        super().__init__(
            f"Communication was temporarily blocked because too many requests were sent to the {url} in a short period of time."  # noqa: E501
        )
        self.token_ratelimit = token_ratelimit
