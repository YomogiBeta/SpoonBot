import os
import secrets
import time

import uuid_utils as uuid
from itsdangerous import TimestampSigner
from oauthlib.oauth2 import WebApplicationClient

from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.constants import DEFAULT_REFRESH_TOKEN_EXPIRES_IN, SPACE
from spoonbot.db.config.MySQLConfig import MySQLConfig
from spoonbot.db.dto.TokenDataDto import TokenDataDto
from spoonbot.db.SpoonUserRepository import SpoonUserRepository
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient

STATE_SIZE = 24
OAUTH_STATE_SIGNE_SALT = "oauth-state-verification"


class SpoonBot:
    async def init(
        self,
        permissions: set[SpoonPermission] | None,
        spoon_client_id: str | None,
        spoon_client_secret: str | None,
        session_secret_key: str | None,
        oauth_redirect_url: str | None,
        country: Country | None,
        mysql_config: MySQLConfig | None,
    ):
        self.permissions = permissions or set()
        self.spoon_client_id = os.getenv("SPOON_CLIENT_ID", spoon_client_id)
        self.spoon_client_secret = os.getenv("SPOON_CLIENR_SECRET", spoon_client_secret)
        self.session_secret_key = os.getenv("SESSION_SECRET_KEY", session_secret_key)
        self.oauth_redirect_url = os.getenv(
            "SPOON_OAUTH_REDIRECT_URL", oauth_redirect_url or ""
        )
        self.target_country = Country(os.getenv("SPOON_BOT_COUNTRY", country))

        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.spoon_client_secret is not None, "Required SPOON_CLIENR_SECRET"
        assert self.session_secret_key is not None, "Required SESSION_SECRET_KEY"
        assert len(self.session_secret_key) > 64, (
            "SESSION_SECRET_KEY must be at least 64 characters long."
        )
        assert len(self.oauth_redirect_url) > 0, "Required SPOON_OAUTH_REDIRECT_URL"
        assert self.target_country is not None, "Required SPOON_BOT_COUNTRY"

        self.constants = ConstantsConfig.create(self.target_country)
        self.oauth_client = WebApplicationClient(self.spoon_client_id)
        self.api_client = await SpoonApiClient.create(self.constants.api_base_url)
        self.api_client.initialize(self.spoon_client_id, self.spoon_client_secret)
        self.spoon_user_repository = SpoonUserRepository()
        await self.spoon_user_repository.initialize(mysql_config)

        self.signer = TimestampSigner(
            self.session_secret_key, salt=OAUTH_STATE_SIGNE_SALT
        )

    def user_authorize_url(self) -> AuthorizeUrl:
        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"

        state = secrets.token_urlsafe(STATE_SIZE)
        signed_state = self.signer.sign(state.encode("utf-8")).decode("utf-8")

        url, _, _ = self.oauth_client.prepare_authorization_request(
            self.constants.oauth_authorize_base_url,
            redirect_url=self.oauth_redirect_url,
            scope=SPACE.join(self.permissions),
            state=signed_state,
        )
        # PKCE implementation is required.
        # However, Spoon developers have not implemented PKCE on their OAuth server.
        # There’s nothing I can do about this.
        return AuthorizeUrl(url, state)

    async def get_authorization(
        self, code: str | None, state: str | None, signed_state: str | None
    ) -> SpoonAuthorization:
        assert code is not None and len(code) > 0, (
            "Error: oauth one time code is none or empty"
        )
        assert state is not None and len(state) > 0, (
            "Error: state is none or empty(By the way, spoon needs to implement PKCE)"
        )

        state_of_session = self.signer.unsign(signed_state or "", max_age=60 * 3)

        assert state == state_of_session, "Forbidden. Invalid state parameter."
        token_respons = await self.api_client.get_token(code, self.oauth_redirect_url)
        epoch_second = int(time.time())
        return SpoonAuthorization(
            id=uuid.uuid7(),
            access_token=token_respons.access_token,
            token_type=token_respons.token_type,
            expire_at=epoch_second + token_respons.expires_in,
            refresh_expire_at=epoch_second + DEFAULT_REFRESH_TOKEN_EXPIRES_IN,
            refresh_token=token_respons.refresh_token,
            scope=token_respons.scope,
            token_status=TokenStatus.DEFAULT,
        )

    async def save_authorization(self, authorization: SpoonAuthorization) -> bool:
        authorization_dto = TokenDataDto(
            id=authorization.id.bytes,
            access_token=authorization.access_token,
            token_type=authorization.token_type,
            expire_at=authorization.expire_at,
            refresh_expire_at=authorization.refresh_expire_at,
            refresh_token=authorization.refresh_token,
            scope=authorization.scope,
            token_status=authorization.token_status,
        )
        return await self.spoon_user_repository.insert_token(authorization_dto)
