# ADR-0027: Optional secure profile - Keycloak, BaSyx Go ABAC, broker ACLs, OPC UA security

- Status: accepted
- Date: 2026-10-03
- Extends: [ADR-0017](0017-aas-operations-delegated.md), [ADR-0021](0021-item-level-dpp-basyx-dpp-api.md),
  [ADR-0023](0023-discovery-registry-resolution-and-gs1-resolver.md), [ADR-0024](0024-plc-opc-ua-server-and-edge-connector.md),
  [ADR-0025](0025-service-decomposition-sustainability-erp.md), [ADR-0028](0028-supplier-environment-batch-aas-federated-footprints.md)

## Context

Everything in the stack was open: anonymous MQTT, unauthenticated AAS / DPP / service APIs, OPC UA
None/Anonymous, Grafana anonymous, Operaton demo/demo, Node-RED without login (O34, O46, O49). That is right for
learning data flows, but a training on Industrie 4.0 must also show how a real plant protects its digital twins:
identities, roles, ownership of data, passport access levels, OT channel security. The default experience must
stay unchanged.

Facts verified against BaSyx Go v1.1.0 (source and running containers, real Keycloak tokens):

- `ABAC_ENABLED` activates OIDC (trust list: exact `iss`, `aud`, JWKS from the discovery document or
  `discoveryUrl`) and the ABAC engine. The AASX preload is imported without a token. Requests without a token are
  anonymous (`GLOBAL=ANONYMOUS`); rules for anonymous also apply to authenticated callers.
- Formulas on `$sm#id`, `$sm#idShort`, `$aas#id` become per-resource query filters: list endpoints return only
  matching submodels, PUT/POST/PATCH/DELETE are checked against the current and the new state. A denied value-only
  PATCH answers HTTP 500 with the text "403 Denied … ABACDENIED" (the value is not written, O58).
- The DPP API composes a passport from the AAS's submodel references. A formula on `$sm` fields breaks its AAS
  read (HTTP 404 "cannot extract alias from column submodel.id_short"); a **fragment filter on
  `$aas#submodels[]`** (role-only formula) hides references and therefore passport sections - this works.
- BaSyx forwards the caller's `Authorization` header to the `invocationDelegation` target (sync and async invoke).
- Mosquitto 2 supports `deny` entries in the ACL file; asyncua 2.0.1 supports Basic256Sha256 SignAndEncrypt,
  user name tokens and a permission ruleset per session user.

## Decision

**Profile mechanics.** A compose override `infra/docker-compose.secure.yml` on top of the unchanged base file
adds Keycloak and switches the existing services (environment, mounted rules, entrypoints) to authenticated mode;
`docker compose -f infra/docker-compose.yml up -d --remove-orphans` returns to the open profile. All application
code reads its security settings from environment variables that only the override sets (`VF_OIDC_*`,
`VF_MQTT_USER/PASSWORD`, `VF_BPMN_USER/PASSWORD`, `VF_OPCUA_*`, `VF_SECURITY_PROFILE`); without them behaviour is
exactly as before. One declarative model, `infra/security.yaml`, generates the realm, the ABAC rules, the trust
list and the broker ACL/accounts (`tools/gen_security_config.py`, checked by a unit test).

**Identity provider.** Keycloak 26.7.4 (`start-dev`, port 8180), realm `virtual-factory` imported from
`infra/keycloak/`: roles operator, quality, maintenance, planner, auditor, authority, recycler, public; one user
per role (password `virtualfactory`); one confidential client per service (client credentials, role
`svc-<name>`, secret `vf-<name>-local-secret`); public client `vf-godot` (password grant + device grant enabled),
`vf-aas-ui` (authorization code + PKCE), confidential `vf-grafana`. Every client has an audience mapper
(`virtual-factory-api`) and a `roles` claim. `KC_HOSTNAME=http://localhost:8180` with dynamic back-channel gives
one issuer for host and compose clients.

**BaSyx Go ABAC** for aas-env, dpp-api and supplier-aas-env (`infra/basyx/security/*.rules.json`):
plant roles read the plant environment; anonymous and `public` read only the public passport submodels;
recycler / authority additionally their passport sets; LineControl `invoke` for operator, planner, maintenance,
`svc-mes`, `svc-maintenance`; write ownership per service after ADR-0025 (MES: workpiece shells and submodels
except CarbonFootprint; sustainability: CarbonFootprint, EnergyConsumption, submodel references; bridge:
OperationalData/EnergyConsumption sinks; maintenance: ConditionMonitoring, Reliability). **DPP access levels**:
public = Nameplate, ContactInformations, CarbonFootprint, ProductCircularity, HandoverDocumentation (matching the
resolver's public page); recycler + composition and BoM; authority + technical, quality and process data;
auditor, quality, MES and sustainability the full passport - implemented as fragment filter on the AAS's
submodel references (submodel idShort as path segment of the id, `vf_common.ids`).

**Supplier environment**: same realm, supplier-scoped rules - only `svc-supplier` writes, plant services and
roles read. Simplification of cross-company trust, which in reality is a federated IdP or a dataspace
(connector, contract, DSP token; O59).

**MQTT**: Mosquitto with password file (plain list hashed by `mosquitto_passwd -U` at container start) and ACL
per topic tree; no anonymous access; only `ops-gateway` may publish commands, the Godot gateway and the edge
publish telemetry/events/acks, consumers read. TLS not enabled (documented). Godot's own MQTT 3.1.1 client sends
user name / password in CONNECT.

**OPC UA**: plc-comm offers only Basic256Sha256 SignAndEncrypt endpoints and user name tokens
(`VF_OPCUA_USERS`), method calls only for `operate` accounts (edge, ops gateway); clients create a self-signed
application certificate and log in (`vf_common.opcua_security`). **AID**: the provisioner of each profile
generates the security definitions of the endpoints that profile runs (`VF_SECURITY_PROFILE=secure`:
SignAndEncrypt/Basic256Sha256 + UserName, MQTT `basic_sc`); the preload is rebuilt at every `up`, so the AAS
always describes the actual endpoint. The checked repository variant is the open one.

**Clients**: `vf_common.auth.ClientCredentials` (`httpx.Auth`, cache, refresh, retry on 401) is the default auth
of `BasyxClient`, `AasResolver.from_env` and the service-to-service HTTP clients; the edge now uses
`RegistryAas` instead of a plain `BasyxClient`. Resource servers (`vf_common.jwt_auth.JwtVerifier`: RS256, JWKS
refresh on unknown `kid`, `iss`, `aud`, `exp`) protect the service APIs (`http_api.Guard`, roles per write
route, alarm acknowledgements carry the token's user) and the ops gateway. **Delegation**: BaSyx forwards the
token, so the ops gateway validates it a second time (defence in depth) instead of trusting the network.
Operaton: authentication on, one engine user per service (no authorization checks); Grafana: generic OAuth with
role mapping, anonymous off; Node-RED: editor login; AAS web UI: OAuth2 infrastructure config.

**Godot**: `--vf-secure` (or `VF_SECURE=1`) logs the training user in with the password grant (`OidcSession`,
public client, refresh before expiry) - a desktop/XR app with known training users needs neither a browser
redirect nor a loopback listener; the device grant (enabled) is the production path for headsets. The token is
sent by every `HttpJson` client; Operaton gets basic auth, MQTT the account `godot`.

**Resolver**: the passport page uses the resolver's own token (role `public`), so it shows exactly the public
sections and names the withheld ones (from `contentSpecificationIds`); `linkType` links to restricted data
(`vf:aas`, `vf:aasDescriptor`) need a realm token - otherwise 401 with the token endpoint as login hint.

## Consequences

- The open profile is unchanged (no variables → no headers, no checks; all default tests green). The secure
  profile is verified by `uv run pytest -m secure` against the running secure stack (real tokens: anonymous write
  refused, MES cannot write CarbonFootprint, sustainability can, public vs. recycler passport, consumer cannot
  publish commands, OPC UA anonymous refused, Grafana requires login).
- Learners see the same data flows with identities attached; ownership rules make wrong writes visible as 403.
- Services fetch one token per 5 minutes; each REST API validates tokens locally (JWKS cached).
- Simplifications (TLS, secrets in the repository, dev-mode Keycloak, password grant, same realm for suppliers,
  self-signed OPC UA certificates without trust lists, unauthenticated backplane, Operaton without
  authorizations, BaSyx events outside ABAC) are listed in [security.md](../architecture/security.md) §6 and as
  O56–O58.

## Alternatives considered

- **Second compose file with copies of all services** - rejected: the profile must switch the existing
  services, not run a parallel stack.
- **Mosquitto JWT auth plugin (go-auth)** - stronger (same identities as HTTP), but an extra image and plugin
  configuration; password file + ACL is built in and robust for training.
- **DPP sections via `$sm#idShort` formulas** - break the DPP API's AAS read (see Context); a separate filtered
  "public passport" AAS per part would duplicate data.
- **Client credentials for an "operator station" in Godot** - a shared secret inside a distributed desktop build
  and no individual operator identity (alarm journal); rejected in favour of user logins.
