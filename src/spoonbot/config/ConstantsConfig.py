from typing import Self

from spoonbot.constants import (
    API_BASE_URL_JP,
    API_BASE_URL_KR,
    OAUTH_AUTHORIZE_BASE_URL_JP,
    OAUTH_AUTHORIZE_BASE_URL_KR,
)
from spoonbot.enums.Country import Country


class ConstantsConfig:
    def __init__(self, oauth_authorize_base_url: str, api_base_url: str) -> None:
        self.oauth_authorize_base_url = oauth_authorize_base_url
        self.api_base_url = api_base_url

    @classmethod
    def create(cls, country: Country) -> Self:
        if country == Country.KR:
            return cls(OAUTH_AUTHORIZE_BASE_URL_KR, API_BASE_URL_KR)
        return cls(OAUTH_AUTHORIZE_BASE_URL_JP, API_BASE_URL_JP)
