"""Test support for the secure profile (unit tests of several services): an RSA signing key with its JWKS
and RS256 access tokens like the Keycloak realm issues them (no identity provider needed)."""

from __future__ import annotations

import base64
import json
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISSUER = "http://localhost:8180/realms/virtual-factory"
AUDIENCE = "virtual-factory-api"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "test-key"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _uint(value: int) -> str:
    return _b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def jwks() -> dict:
    numbers = KEY.public_key().public_numbers()
    return {"keys": [{"kid": KID, "kty": "RSA", "alg": "RS256", "use": "sig", "n": _uint(numbers.n),
                      "e": _uint(numbers.e)}]}


def token(roles: list[str], name: str = "operator1", key=KEY, kid: str = KID, **claims) -> str:
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": f"id-{name}", "preferred_username": name,
               "exp": now + 300, "iat": now, "realm_access": {"roles": roles}, **claims}
    header = _b64(json.dumps({"alg": "RS256", "kid": kid, "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = key.sign(f"{header}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{body}.{_b64(signature)}"


def verifier():
    from vf_common.jwt_auth import JwtVerifier
    return JwtVerifier(ISSUER, "http://keycloak/certs", AUDIENCE, fetch=lambda url: jwks())
