"""Endpoint security as described in the Asset Interfaces Description (ADR-0027).

The AID must describe the security the endpoints really have, and that depends on the compose profile. The
one-shot provisioner of each profile therefore generates the matching variant (the preload is rebuilt at
every `up`): VF_SECURITY_PROFILE=secure (set by infra/docker-compose.secure.yml) -> OPC UA Basic256Sha256
SignAndEncrypt with UserName tokens, MQTT username/password (WoT basic scheme); default "open" ->
OPC UA None/Anonymous, MQTT nosec. The repository's checked AASX and docs use the open variant."""

from __future__ import annotations

import os

SECURITY_POLICY_NONE = "http://opcfoundation.org/UA/SecurityPolicy#None"
SECURITY_POLICY_BASIC256SHA256 = "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"


def secure() -> bool:
    return os.environ.get("VF_SECURITY_PROFILE", "open").strip().lower() == "secure"


def mqtt_scheme() -> tuple[str, dict]:
    """(securityDefinitions entry, its values) of the MQTT interface (the broker of the UNS)."""
    if secure():  # user name / password in CONNECT, one account per client (infra/security.yaml)
        return "basic_sc", {"scheme": "basic", "in": "auto"}
    return "nosec_sc", {"scheme": "nosec"}


def opcua_definitions() -> dict:
    """Channel and user token security of the OPC UA server (communication module, plc_comm)."""
    if secure():
        return {"opcua_channel_sc": {"scheme": "ua_channelsec", "uav_securityMode": "SignAndEncrypt",
                                     "uav_securityPolicy": SECURITY_POLICY_BASIC256SHA256},
                "opcua_authentication_sc": {"scheme": "ua_authentication",
                                            "uav_userIdentityToken": "UserName"}}
    return {"opcua_channel_sc": {"scheme": "ua_channelsec", "uav_securityMode": "None",
                                 "uav_securityPolicy": SECURITY_POLICY_NONE},
            "opcua_authentication_sc": {"scheme": "ua_authentication", "uav_userIdentityToken": "Anonymous"}}
