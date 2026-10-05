import base64

from spoonbot.httpclient.APIClient import APIClient
from spoonbot.httpclient.dto.TokenResponse import TokenResponse


class SpoonApiClient(APIClient):
    client_id: str
    client_secret: str

    def initialize(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_token(self, code: str, redirect_uri: str) -> TokenResponse:
        return await self.post(
            endpoint="oauth/token",
            body={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Authorization": self._authorize_token()},
            response_type=TokenResponse,
        )

    def _authorize_token(self) -> str:
        token_str = f"{self.client_id}:{self.client_secret}"
        token = base64.b64encode(token_str.encode("utf-8")).decode("utf-8")
        return f"Basic {token}"
