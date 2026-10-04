# Security concept (secure profile)

The training stack is **open by default** (anonymous MQTT, unauthenticated REST APIs, OPC UA None/Anonymous):
learners should see data flows, not fight logins. The optional **secure profile**
([ADR-0027](../adr/0027-optional-security-profile-keycloak-abac.md)) switches the *same* services to an
authenticated, role-based mode that mirrors a realistic Industrie 4.0 deployment:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.secure.yml up -d --build
```

Single source of the security model: [`infra/security.yaml`](../../infra/security.yaml) (roles, users, clients,
ABAC grants, broker ACLs). `uv run tools/gen_security_config.py [--check]` generates the Keycloak realm, the BaSyx
Go access rules and trust list and the Mosquitto ACL / account list from it; `tools/tests/test_security_config.py`
checks that the generated files are current.

## 1. Threat model (light)

| Asset | Threats considered | Mitigation in the secure profile |
|---|---|---|
| Line control (LineControl operations, UNS commands, OPC UA methods) | unauthorised start/stop, spoofed commands, command injection from a learner's flow | token + role for `invoke` (ABAC) **and** in the ops gateway; only `ops-gateway` may publish `cmd` topics; OPC UA method calls only for `operate` accounts |
| Digital twin data (AAS, submodels) | tampering by a compromised or buggy service, disclosure | write ownership per service (ABAC), read only for plant roles; anonymous sees public passport sections only |
| Product passports (DPP) | disclosure of composition / BoM / quality data | DPP API filters passport sections per role (public, recycler, authority, auditor) |
| Telemetry / events (UNS) | spoofed telemetry, eavesdropping | broker accounts per client, write ACL per topic tree (devices/edge publish telemetry, consumers read-only) |
| Supplier batch data | unauthorised writes into the supplier environment | only `svc-supplier` writes; plant services and plant roles read |
| Operator actions (alarm acknowledge, maintenance windows, orders) | repudiation ("free-text operator"), unauthorised changes | bearer token required, role per route, the alarm journal records the token's user |
| Dashboards, process engine, sandbox | anonymous read of all history, process manipulation | Grafana login via Keycloak (anonymous off), Operaton basic auth per service, Node-RED editor login |

Out of scope (documented simplifications, §6): network attackers on the Docker host (no TLS), stolen local
default secrets, denial of service, supply chain, physical access to the backplane port.

## 2. Trust boundaries

```text
 Browser / Godot (host)            ─── TB1: host → compose stack (HTTP 8091/8093/8096/…, ws 9001, opc.tcp 4840)
   │ user token (password grant / auth code + PKCE)
   ▼
 Keycloak realm "virtual-factory" (8180) ─ issues RS256 JWTs (iss http://localhost:8180/realms/virtual-factory,
   ▲                                       aud virtual-factory-api, realm roles in realm_access.roles)
   │ client credentials (one confidential client per service)
 IT services (mes, bridge, sustainability, …) ─ TB2: service → resource server (BaSyx Go ABAC, ops gateway,
   │                                                  service REST APIs validate the JWT themselves)
 OT edge (edge, ops-gateway) ── TB3: IT → OT: OPC UA Basic256Sha256 SignAndEncrypt + user name, MQTT ACLs
   ▼
 plc-comm ◄── backplane 4841 (inside the "control cabinet", not secured, O57) ── Godot PLC CPU
 Supplier environment (8191) ── TB4: cross-company: same realm, supplier-scoped rules (simplified federation)
```

## 3. Roles × resources

Realm roles (people): `operator`, `quality`, `maintenance`, `planner`, `auditor`, `authority`, `recycler`,
`public`; service accounts carry `svc-<service>` (the resolver additionally `public`). Users: one per role
(`operator1`, `quality1`, `maintenance1`, `planner1`, `auditor1`, `authority1`, `recycler1`).

| Resource | anonymous / public | operator | quality | maintenance | planner | auditor | authority | recycler |
|---|---|---|---|---|---|---|---|---|
| AAS env 8091: shells, submodels, registry, CDs | public passport submodels¹ | read | read | read | read | read | public + authority set² | public + recycler set³ |
| LineControl operations (invoke) | – | ✓ | – | ✓ | ✓ | – | – | – |
| DPP API 8093 | public sections¹ | public | **all** | public | public | **all** | + composition, BoM, technical data, quality, processes | + composition, BoM |
| Supplier env 8191 | – | read | read | read | read | read | read | read |
| Alarms 8099 (ack, shelve) | – | ✓ | read | ✓ | read | read | read | read |
| ERP 8098 (orders, settings) | – | read | read | windows | ✓ | read | read | read |
| Maintenance 8094 (evaluate, settings) | – | read | read | ✓ | ✓ | read | read | read |
| Grafana 3002 | – | Viewer | Editor | Editor | Editor | Viewer | – | – |
| Resolver restricted links (`vf:aas`, `vf:aasDescriptor`) | 401 + login hint | any realm token | … | … | … | … | … | … |

¹ Nameplate, ContactInformations, CarbonFootprint, ProductCircularity, HandoverDocumentation, DppMetadata
(attachments of these, e.g. the inspection certificate, are therefore public too).
² ¹ + ProductMaterialComposition, HierarchicalStructures, TechnicalData, QualityInspection, ExecutedProcesses.
³ ¹ + ProductMaterialComposition, HierarchicalStructures. "read" in the service rows = any valid realm token.
Authenticated callers also match the anonymous rules (BaSyx treats public grants as a baseline).

Service write ownership (ADR-0025, enforced by ABAC on create/update/delete):

| Service account | May write (main AAS environment) |
|---|---|
| `svc-mes` | workpiece shells `…/aas/WP_*`; workpiece submodels `…/sm/WP_*` **except CarbonFootprint** (delete: all of the workpiece); KLT `HierarchicalStructures`; LINE01 `ProcessVariablesForManufacturingKPICalculation`; concept descriptions; invoke LineControl |
| `svc-sustainability` | workpiece `CarbonFootprint` (create/update), submodel references of workpiece shells, `EnergyConsumption`, concept descriptions |
| `svc-bridge` | `OperationalData`, `EnergyConsumption` (AIMC sinks) |
| `svc-maintenance` | `ConditionMonitoring`, `Reliability`; invoke LineControl |
| `svc-supplier` | everything in the supplier environment (batch AAS) - nothing in the plant's |
| `svc-ops-gateway`, `svc-edge` | read only (Control Component, AID) |
| `svc-resolver` | read discovery / registry, public passport sections (role `public`) |

MQTT accounts (`infra/mosquitto/secure/acl`): `godot` writes telemetry, events, acks, session (not
`maintenance/#`, `sandbox/#`), reads commands and AAS events; `edge` writes PLC01 telemetry/events/acks, reads
PLC01 commands; **only `ops-gateway` writes `{root}/+/cmd/+`**; `maintenance` writes `{root}/maintenance/#`;
`basyx` writes `vf/basyx/#`; `mes`, `bridge`, `historian`, `alarms`, `sustainability` read; `nodered` reads and
writes only `{root}/sandbox/#`; `explorer` reads everything (MQTT Explorer).

OPC UA (plc-comm): `edge` and `ops-gateway` (operate: read, subscribe, call methods), `explorer` (read only);
anonymous sessions and SecurityPolicy None are refused.

## 4. Token flows

| Flow | Who | Grant | Notes |
|---|---|---|---|
| Service → BaSyx, ERP, supplier portal, DPP API | every Python service | client credentials (`vf_common.auth.ClientCredentials`, `httpx.Auth`) | token cached until 30 s before expiry, one retry with a fresh token on 401; env `VF_OIDC_TOKEN_URL/CLIENT_ID/CLIENT_SECRET` |
| AAS operation → ops gateway | BaSyx Go | caller's token **forwarded** by BaSyx to the delegation target (verified, sync and async) | the gateway validates it again (`vf_common.jwt_auth`) and checks the commander roles - defence in depth |
| Service REST APIs, resolver | erp, alarms, maintenance, sustainability, supplier, resolver | resource server: RS256 signature (JWKS), `iss`, `aud`, `exp` | `vf_common.http_api.Guard`; `/health` stays public |
| Godot training UI | training user | password grant, public client `vf-godot` (`OidcSession`, refresh before expiry) | token sent by every `HttpJson` client; Operaton with basic auth (`godot`); broker account `godot` |
| AAS web UI, Grafana | browser | authorization code + PKCE (`vf-aas-ui` public, `vf-grafana` confidential) | Grafana maps realm roles to Viewer/Editor, users without a mapped role cannot log in |
| Passport page | anyone | none (resolver's own token, role `public`) | restricted links answer 401 with the token endpoint as login hint |

Issuer handling: Keycloak runs with `KC_HOSTNAME=http://localhost:8180` and dynamic back-channel URLs, so all
tokens carry the same `iss` whether they were obtained from the host or from `http://keycloak:8080` inside
compose; BaSyx loads the OIDC metadata from `discoveryUrl` (compose host), the services fetch the JWKS from
`VF_OIDC_JWKS_URL`.

## 5. AID and the profile

The Asset Interfaces Description must describe the real endpoint security. The one-shot provisioner of each
profile builds the preload: `VF_SECURITY_PROFILE=secure` → OPC UA `opcua_channel_sc` = SignAndEncrypt /
Basic256Sha256, `opcua_authentication_sc` = UserName; MQTT `basic_sc` (user name / password); open profile →
None / Anonymous / `nosec_sc`. The repository's checked AASX and docs show the open variant.

## 6. Simplifications vs. production

| Here (training) | Production |
|---|---|
| plain HTTP, MQTT and WebSocket inside and to the host; OPC UA encrypted but certificates self-signed, regenerated at start, not validated (no trust lists) | TLS everywhere (reverse proxy / service mesh with mTLS, MQTT 8883/wss, OPC UA GDS-managed PKI and trust lists) |
| secrets and passwords as local defaults in the repository (`infra/security.yaml`, compose file, `backend.json`) | secret manager (Vault, Kubernetes secrets, Docker secrets), per-environment values, no secrets in git |
| Keycloak dev mode, realm re-imported at every start, keys regenerate | persistent Keycloak cluster with database, planned key rotation (JWKS refresh is implemented), short token lifetimes, refresh token rotation |
| password grant for the Godot app | device authorization grant (headsets) or authorization code + PKCE with a system browser (RFC 8252) |
| supplier environment trusts the plant's realm with supplier-scoped rules | each company runs its own IdP; cross-company access via identity federation or a dataspace (EDC, contract negotiation, DSP tokens), O59 |
| Operaton: per-service basic-auth users, no authorization checks | Keycloak SSO plugin, engine authorizations per process definition / group |
| BaSyx MQTT eventing carries change events to every account with read on `vf/basyx/#` (bypasses ABAC) | separate event topics per audience or an authorised event feed |
| backplane link Godot ↔ plc-comm (4841) unauthenticated | inside the controller - not reachable from the network |
| ABAC policy file imported at start (`ABAC_POLICY_FILE_IMPORT=always`) | managed policy versions (BaSyx ABAC management API), reviewed changes, audit log |

Open issues: O56–O58 in [open-issues.md](../open-issues.md); O34, O46 and O49 are mitigated by the profile.
