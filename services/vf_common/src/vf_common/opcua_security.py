"""OPC UA security of the secure profile (ADR-0027, open issue O49): SecurityPolicy Basic256Sha256 with
MessageSecurityMode SignAndEncrypt and user name / password tokens, for the communication module's server
(plc_comm) and its clients (edge, ops gateway).

Environment (all off by default - the open profile keeps None/Anonymous):
    VF_OPCUA_SECURITY   "sign_encrypt" (Basic256Sha256, SignAndEncrypt) | "none" (default)
    VF_OPCUA_USER / VF_OPCUA_PASSWORD   user token of a client
    VF_OPCUA_USERS      server accounts "name:password:operate|read,..." (operate: may call methods)
    VF_OPCUA_PKI_DIR    where the self-signed application certificate + key are kept (default: temp dir)

Simplification (O57): every application creates its own self-signed certificate at start; the client takes
the server certificate from GetEndpoints and the server accepts any client certificate (no trust lists,
no CA). The channel is encrypted and the session authenticated by the user token."""

from __future__ import annotations

import os
import socket
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from asyncua import Client, Server, ua
from asyncua.crypto import security_policies
from asyncua.crypto.cert_gen import setup_self_signed_certificate
from asyncua.crypto.permission_rules import USER_TYPES, PermissionRuleset, User, UserRole
from cryptography.x509.oid import ExtendedKeyUsageOID

SIGN_ENCRYPT = "sign_encrypt"
_CALL = ua.NodeId(ua.ObjectIds.CallRequest_Encoding_DefaultBinary)
_WRITE = ua.NodeId(ua.ObjectIds.WriteRequest_Encoding_DefaultBinary)


@dataclass(frozen=True)
class OpcUaSecurity:
    mode: str = "none"
    user: str = ""
    password: str = ""
    accounts: dict[str, tuple[str, str]] = field(default_factory=dict)   # name -> (password, operate|read)
    pki_dir: str = ""

    @property
    def secure(self) -> bool:
        return self.mode == SIGN_ENCRYPT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> OpcUaSecurity:
        env = os.environ if env is None else env
        accounts = {}
        for entry in filter(None, (e.strip() for e in env.get("VF_OPCUA_USERS", "").split(","))):
            name, password, *role = entry.split(":")
            accounts[name] = (password, role[0] if role else "read")
        mode = env.get("VF_OPCUA_SECURITY", "none").strip().lower() or "none"
        return cls(mode, env.get("VF_OPCUA_USER", ""), env.get("VF_OPCUA_PASSWORD", ""), accounts,
                   env.get("VF_OPCUA_PKI_DIR", ""))


async def _certificate(security: OpcUaSecurity, app_uri: str, name: str, use) -> tuple[Path, Path]:
    pki = Path(security.pki_dir or tempfile.gettempdir()) / "vf-opcua-pki"
    pki.mkdir(parents=True, exist_ok=True)
    key, cert = pki / f"{name}-key.pem", pki / f"{name}-cert.der"
    await setup_self_signed_certificate(key, cert, app_uri, socket.gethostname(), [use],
                                        {"countryName": "DE", "organizationName": "Virtual Factory",
                                         "commonName": name})
    return cert, key


async def secure_client(client: Client, security: OpcUaSecurity, name: str = "vf-service") -> None:
    """Before connect(): Basic256Sha256 SignAndEncrypt + user token (no-op in the open profile)."""
    if security.user:
        client.set_user(security.user)
        client.set_password(security.password)
    if not security.secure:
        return
    app_uri = f"urn:virtual-factory:{name}"
    client.application_uri = app_uri
    cert, key = await _certificate(security, app_uri, name, ExtendedKeyUsageOID.CLIENT_AUTH)
    await client.set_security(security_policies.SecurityPolicyBasic256Sha256, str(cert), str(key),
                              mode=ua.MessageSecurityMode.SignAndEncrypt)


class AccountManager:
    """User name / password check against VF_OPCUA_USERS; anonymous sessions are refused."""

    def __init__(self, accounts: dict[str, tuple[str, str]]):
        self.accounts = accounts

    def get_user(self, iserver, username=None, password=None, certificate=None) -> User | None:
        account = self.accounts.get(username or "")
        if account is None or password is None or account[0] != password:
            return None
        return User(role=UserRole.User, name=f"{username}:{account[1]}")


class RoleRuleset(PermissionRuleset):
    """Read, browse and subscribe for every account; method calls only for "operate" accounts; no writes."""

    def __init__(self):
        self.allowed = set(map(ua.NodeId, USER_TYPES)) - {_CALL, _WRITE}

    def check_validity(self, user, action_type_id, body) -> bool:
        if user is None or user.role != UserRole.User:
            return False
        if action_type_id == _CALL:
            return str(user.name or "").endswith(":operate")
        return action_type_id in self.allowed


async def secure_server(server: Server, security: OpcUaSecurity, app_uri: str) -> None:
    """After init(), before start: only Basic256Sha256 SignAndEncrypt endpoints and user name tokens."""
    if not security.secure:
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        return
    cert, key = await _certificate(security, app_uri, "plc-comm", ExtendedKeyUsageOID.SERVER_AUTH)
    await server.load_certificate(str(cert))
    await server.load_private_key(str(key))
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt], RoleRuleset())
    server.set_identity_tokens([ua.UserNameIdentityToken])
    server.iserver.set_user_manager(AccountManager(security.accounts))
