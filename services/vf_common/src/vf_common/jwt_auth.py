"""Bearer token validation for the services' own HTTP endpoints (secure profile, ADR-0027).

`JwtVerifier` checks compact JWS access tokens of the realm: RS256 signature against the realm's JWKS (fetched
from VF_OIDC_JWKS_URL, refreshed when a token names an unknown key), `iss` (VF_OIDC_ISSUER, exact match),
`aud` (VF_OIDC_AUDIENCE), `exp`/`nbf` with a small leeway. Roles are the realm roles
(`realm_access.roles`). Only `cryptography` is needed (already a dependency of asyncua).
`verifier_from_env()` returns None when VF_OIDC_ISSUER is not set (open profile: no checks)."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

log = logging.getLogger("vf.jwt")


class InvalidToken(ValueError):
    """Missing, malformed, expired or untrusted token (HTTP 401)."""


@dataclass(frozen=True)
class Principal:
    subject: str
    name: str
    roles: frozenset[str]
    claims: dict

    def has_any(self, roles) -> bool:
        return bool(self.roles & set(roles))


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _int(segment: str) -> int:
    return int.from_bytes(_b64(segment), "big")


def principal(claims: dict) -> Principal:
    roles = frozenset((claims.get("realm_access") or {}).get("roles") or [])
    name = claims.get("preferred_username") or claims.get("azp") or claims.get("sub") or "unknown"
    return Principal(str(claims.get("sub", "")), str(name), roles, claims)


class JwtVerifier:
    def __init__(self, issuer: str, jwks_url: str, audience: str | None = None, leeway_s: float = 30.0,
                 clock: Callable[[], float] = time.time, fetch: Callable[[str], dict] | None = None):
        self.issuer, self.jwks_url, self.audience, self.leeway_s = issuer, jwks_url, audience, leeway_s
        self.clock = clock
        self._fetch = fetch or (lambda url: httpx.get(url, timeout=10.0).raise_for_status().json())
        self._keys: dict[str, rsa.RSAPublicKey] = {}
        self._lock = threading.Lock()

    def verify(self, token: str) -> Principal:
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
            header, claims = json.loads(_b64(header_b64)), json.loads(_b64(payload_b64))
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidToken("malformed token") from exc
        if header.get("alg") != "RS256":
            raise InvalidToken(f"unsupported algorithm {header.get('alg')}")
        key = self._key(str(header.get("kid", "")))
        try:
            key.verify(_b64(signature_b64), f"{header_b64}.{payload_b64}".encode(), padding.PKCS1v15(),
                       hashes.SHA256())
        except InvalidSignature as exc:
            raise InvalidToken("bad signature") from exc
        self._check_claims(claims)
        return principal(claims)

    def _check_claims(self, claims: dict) -> None:
        now = self.clock()
        if claims.get("iss") != self.issuer:
            raise InvalidToken(f"untrusted issuer {claims.get('iss')}")
        if float(claims.get("exp", 0)) + self.leeway_s < now:
            raise InvalidToken("token expired")
        if float(claims.get("nbf", 0)) - self.leeway_s > now:
            raise InvalidToken("token not yet valid")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.audience and self.audience not in audiences:
            raise InvalidToken(f"token not issued for {self.audience}")

    def _key(self, kid: str) -> rsa.RSAPublicKey:
        with self._lock:
            if kid not in self._keys:  # unknown key: the realm may have rotated its keys
                try:
                    jwks = self._fetch(self.jwks_url)
                except (httpx.HTTPError, ValueError) as exc:
                    raise InvalidToken(f"JWKS {self.jwks_url} unavailable: {exc}") from exc
                self._keys = {k["kid"]: rsa.RSAPublicNumbers(_int(k["e"]), _int(k["n"])).public_key()
                              for k in jwks.get("keys", [])
                              if k.get("kty") == "RSA" and k.get("use") != "enc"}
            if kid not in self._keys:
                raise InvalidToken(f"unknown signing key {kid}")
            return self._keys[kid]


def bearer(authorization: str | None) -> str:
    """The token of an `Authorization: Bearer <token>` header."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InvalidToken("bearer token required")
    return token.strip()


def verifier_from_env(env: Mapping[str, str] | None = None) -> JwtVerifier | None:
    env = os.environ if env is None else env
    issuer = env.get("VF_OIDC_ISSUER", "")
    if not issuer:
        return None
    jwks = env.get("VF_OIDC_JWKS_URL") or f"{issuer}/protocol/openid-connect/certs"
    return JwtVerifier(issuer, jwks, env.get("VF_OIDC_AUDIENCE") or None)
