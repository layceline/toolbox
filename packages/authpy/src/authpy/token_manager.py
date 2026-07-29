"""OAuth2 client-credentials token retrieval with in-memory caching."""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import requests

# Shaved off the reported lifetime so a token handed out here is still valid by
# the time the caller actually uses it.
EXPIRY_SAFETY_MARGIN_S = 5


class TokenManager:
    """
    Fetch access tokens from an OAuth2 `client_credentials` token endpoint.

    Tokens are cached per scope set for the lifetime of the instance.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        endpoint: str,
        token_path: str = "/oauth2/token",
        timeout: float = 5.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.endpoint = endpoint.rstrip("/")
        self.token_path = token_path
        self.timeout = timeout
        self.tokens: dict[str, dict] = {}

    def get_token(self, scopes: list[str]) -> str | None:
        request_time = datetime.now(tz=UTC)
        scopes_str = " ".join(scopes)

        cached = self.tokens.get(scopes_str)
        if cached and request_time < cached["expires_at"]:
            return cached["token"]

        response = requests.post(
            url=f"{self.endpoint}{self.token_path}",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials", "scope": scopes_str},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )

        content = response.json()
        if response.status_code != HTTPStatus.OK or "access_token" not in content:
            return None

        self.tokens[scopes_str] = {
            "token": content["access_token"],
            "expires_at": request_time + timedelta(seconds=content["expires_in"] - EXPIRY_SAFETY_MARGIN_S),
        }
        return content["access_token"]
