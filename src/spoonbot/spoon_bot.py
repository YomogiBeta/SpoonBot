import os
import secrets

from oauthlib.oauth2 import WebApplicationClient

from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission
from spoonbot.httpclient.dto.Token import Token
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient

STATE_SIZE = 24


class SpoonBot:
    async def init(
        self,
        permissions: set[SpoonPermission] | None,
        spoon_client_id: str | None,
        spoon_client_secret: str | None,
        oauth_redirect_url: str | None,
        country: Country | None,
    ):
        self.permissions = permissions or set()
        self.spoon_client_id = os.getenv("SPOON_CLIENT_ID", spoon_client_id)
        self.spoon_client_secret = os.getenv("SPOON_CLIENR_SECRET", spoon_client_secret)
        self.oauth_redirect_url = os.getenv(
            "SPOON_OAUTH_REDIRECT_URL", oauth_redirect_url
        )
        self.target_country = Country(os.getenv("SPOON_BOT_COUNTRY", country))

        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.spoon_client_secret is not None, "Required SPOON_CLIENR_SECRET"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"
        assert self.target_country is not None, "Required SPOON_BOT_COUNTRY"

        self.constants = ConstantsConfig.create(self.target_country)
        self.oauth_client = WebApplicationClient(self.spoon_client_id)
        self.api_client = await SpoonApiClient.create(self.constants.api_base_url)
        self.api_client.initialize(self.spoon_client_id, self.spoon_client_secret)

    def user_authorize_url(self) -> AuthorizeUrl:
        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"

        state = secrets.token_urlsafe(STATE_SIZE)

        url, _, _ = self.oauth_client.prepare_authorization_request(
            self.constants.oauth_authorize_base_url,
            redirect_url=self.oauth_redirect_url,
            scope=self.permissions,
            state=state,
        )
        # PKCE implementation is required.
        # However, Spoon developers have not implemented PKCE on their OAuth server.
        # There’s nothing I can do about this.
        return AuthorizeUrl(url, state)

    async def get_accsess_token(
        self, code: str, state: str, state_of_session: str
    ) -> Token:
        assert code is not None and len(code) > 0, (
            "Error: oauth one time code is none or empty"
        )
        assert state is not None and len(state) > 0, (
            "Error: state is none or empty(By the way, spoon needs to implement PKCE)"
        )
        assert state == state_of_session, "Forbidden. Invalid state parameter."
        return await self.api_client.get_token(code, self.oauth_redirect_url)
