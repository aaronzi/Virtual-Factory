"""OAuth 2.0 client credentials for the services (secure profile, ADR-0027).

`ClientCredentials` is an `httpx.Auth`: it fetches an access token from the token endpoint, caches it until
shortly before it expires and retries a request once with a fresh token when the resource server answers 401
(e.g. after a Keycloak restart). `service_auth()` builds it from the environment and returns None when the
variables are not set - the default (open) profile then sends no Authorization header at all.

Environment: VF_OIDC_TOKEN_URL (token endpoint as reachable from the service), VF_OIDC_CLIENT_ID,
VF_OIDC_CLIENT_SECRET. Basic-auth credentials of the BPMN engine: VF_BPMN_USER / VF_BPMN_PASSWORD."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Generator, Mapping

import httpx

log = logging.getLogger("vf.auth")


class TokenError(RuntimeError):
    """The token endpoint refused the client or could not be reached."""


class ClientCredentials(httpx.Auth):
    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str | None = None,
                 skew_s: float = 30.0, clock: Callable[[], float] = time.monotonic,
                 transport: httpx.BaseTransport | None = None):
        self.token_url, self.client_id, self.client_secret = token_url, client_id, client_secret
        self.scope, self.skew_s, self.clock = scope, skew_s, clock
        self._http = httpx.Client(timeout=10.0, transport=transport)
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    def token(self, refresh: bool = False) -> str:
        """Current access token (cached; fetched again when it expires within `skew_s` or on `refresh`)."""
        with self._lock:
            if refresh or self._token is None or self.clock() >= self._expires:
                self._token, lifetime = self._fetch()
                self._expires = self.clock() + max(lifetime - self.skew_s, lifetime / 2)
            return self._token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token()}"
        response = yield request
        if response.status_code == 401:
            request.headers["Authorization"] = f"Bearer {self.token(refresh=True)}"
            yield request

    def _fetch(self) -> tuple[str, float]:
        data = {"grant_type": "client_credentials", "client_id": self.client_id,
                "client_secret": self.client_secret, **({"scope": self.scope} if self.scope else {})}
        try:
            response = self._http.post(self.token_url, data=data)
        except httpx.HTTPError as exc:
            raise TokenError(f"token endpoint {self.token_url} unreachable: {exc}") from exc
        if response.status_code != 200:
            raise TokenError(f"token request of {self.client_id} refused: HTTP {response.status_code} "
                             f"{response.text[:200]}")
        body = response.json()
        log.debug("token for %s valid for %s s", self.client_id, body.get("expires_in"))
        return body["access_token"], float(body.get("expires_in") or 60)


_shared: dict[tuple[str, str], ClientCredentials] = {}
_shared_lock = threading.Lock()


def service_auth(env: Mapping[str, str] | None = None) -> ClientCredentials | None:
    """Client-credentials auth of this service from the environment, or None (open profile). One shared
    instance per client, so all clients of a process reuse the cached token."""
    env = os.environ if env is None else env
    url, client_id = env.get("VF_OIDC_TOKEN_URL", ""), env.get("VF_OIDC_CLIENT_ID", "")
    if not url or not client_id:
        return None
    with _shared_lock:
        if (url, client_id) not in _shared:
            secret = env.get("VF_OIDC_CLIENT_SECRET", "")
            _shared[(url, client_id)] = ClientCredentials(url, client_id, secret)
        return _shared[(url, client_id)]


def bpmn_auth(env: Mapping[str, str] | None = None) -> httpx.BasicAuth | None:
    """Basic auth for the Operaton REST API (secure profile: one engine user per service), or None."""
    env = os.environ if env is None else env
    user = env.get("VF_BPMN_USER", "")
    return httpx.BasicAuth(user, env.get("VF_BPMN_PASSWORD", "")) if user else None


def mqtt_credentials(env: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """(username, password) of the broker account (secure profile: VF_MQTT_USER / VF_MQTT_PASSWORD)."""
    env = os.environ if env is None else env
    user = env.get("VF_MQTT_USER", "")
    return (user, env.get("VF_MQTT_PASSWORD", "")) if user else None
