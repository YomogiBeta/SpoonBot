from spoonbot.dto.RateLimit import RateLimit


class DailyRequestLimitException(Exception):
    token_ratelimit: RateLimit

    def __init__(self, token_ratelimit: RateLimit, url: str):
        super().__init__(
            f"""This bot has exceeded its daily request limit. Please wait until the next day, when the request limit resets, before sending more requests.
            Try Request url: {url}"""  # noqa: E501
        )
        self.token_ratelimit = token_ratelimit
