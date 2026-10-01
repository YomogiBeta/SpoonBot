import os
import secrets
import urllib.parse
from oauthlib.oauth2 import WebApplicationClient

from spoonbot.Constants import SPACE
from spoonbot.config.ConstantsConfig import ConstantsConfig
from spoonbot.dto.AuthorizeUrl import AuthorizeUrl
from spoonbot.enums.Country import Country
from spoonbot.enums.SpoonPermission import SpoonPermission

STATE_SIZE = 24

class SpoonBot():
    def __init__(self,
                 permissions: set[SpoonPermission] | None,
                 spoon_client_id: str | None,
                 spoon_client_secret: str | None,
                 oauth_redirect_url: str | None,
                 country: Country | None):
        self.permissions = permissions or set()
        self.spoon_client_id = os.getenv("SPOON_CLIENT_ID", spoon_client_id)
        self.spoon_client_secret = os.getenv("SPOON_CLIENR_SECRET", spoon_client_secret)
        self.oauth_redirect_url = os.getenv("SPOON_OAUTH_REDIRECT_URL", oauth_redirect_url)
        self.target_country = Country(os.getenv("SPOON_BOT_COUNTRY", country))
        
        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.spoon_client_secret is not None, "Required SPOON_CLIENR_SECRET"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"
        assert self.target_country is not None, "Required SPOON_BOT_COUNTRY"
        
        self.constants = ConstantsConfig.create(self.target_country)
        self.oauth_client = WebApplicationClient(self.spoon_client_id)
        
    def user_authorize_url(self) -> AuthorizeUrl:
        assert self.spoon_client_id is not None, "Required SPOON_CLIENT_ID"
        assert self.oauth_redirect_url is not None, "Required SPOON_OAUTH_REDIRECT_URL"
        
        state = secrets.token_urlsafe(STATE_SIZE)
        url =  self.constants.oauth_authorize_base_url \
            + "?response_type=code" \
            + f"&client_id={urllib.parse.quote_plus(self.spoon_client_id)}" \
            + f"&redirect_uri={urllib.parse.quote_plus(self.oauth_redirect_url)}" \
            + f"&scope={self._encode_permissions()}" \
            + f"&state={state}"

        # PKCE implementation is required. However, Spoon developers have not implemented PKCE on their OAuth server. There’s nothing I can do about this.  
        # TODO: Store state
        return AuthorizeUrl(url, state)

    def _encode_permissions(self):
        assert len(self.permissions) > 0, "At least one permission must be set"
        return urllib.parse.quote(SPACE.join(self.permissions))
    
    def get_accsess_token(self, code: str, state: str):
        assert code is not None and len(code) > 0, "Error: oauth one time code is none or empty"
        assert state is not None and len(state) > 0, "Error: state is none or empty(By the way, spoon needs to implement PKCE)"
        
        # TODO: Verify state in db