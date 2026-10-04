# Edge and IT services

All services are Python packages in `services/` (one image `vf-services:dev`, repository mounted read-only at `/repo`)
and run in the compose stack `infra/docker-compose.yml`. The Godot simulation runs on the host.

```text
Godot (FMUs, PLC) ──UNS/MQTT──► bridge ──REST $value──► BaSyx Go (AAS) ◄──REST── mes ◄──external tasks── Operaton
       ▲                          ▲                        │      ▲               │  ▲                    (BPMN)
       │                          └─── AIMC/AID (REST) ────┘      │ invoke        │  └──UNS events (MQTT)
       └──────UNS commands─────── ops-gateway ◄── delegation ─────┘ (LineControl) │
       │                                                          ◄──────────────┘ invoke LineControl
       └──UNS telemetry (MQTT)──► historian ──line protocol──► InfluxDB 3 ◄──SQL── sustainability (PCF), clients
                                                                                 via the AAS TimeSeries LinkedSegment
                                                                                 and Grafana dashboards (:3002)

erp ──message OrderReleased──► Operaton ──external tasks──► mes (order, workpiece-*), sustainability (pcf-calculate)
 ▲                                                                  │ CarbonFootprint submodel ──► BaSyx Go
 └──── OperationsPerformance (good, scrap, consumed lots) ──── mes ◄┘
UNS (alarm word, packml_state, events, commands) ──► alarms ──► TimescaleDB ◄── Grafana "Alarms & events"
InfluxDB ──SQL──► maintenance ──UNS {root}/maintenance/...──► historian;  maintenance ──► ConditionMonitoring (AAS),
   MaintenanceOrder (Operaton) ──► ERP maintenance window, LineControl Maintain / SetUnitMode (ops gateway)
```

Data ownership (ADR-0025/0026): the MES composes the workpiece AAS/passport and owns all its submodels except the
CarbonFootprint (sustainability); the sustainability service also owns the derived EnergyConsumption values; the
ERP owns orders and batch records; the alarms service owns alarm states and the alarm/event journal. The supplier
portal owns the batch AAS in the separately operated supplier AAS environment (ADR-0028). The maintenance service
owns the ConditionMonitoring submodel and the observed Reliability sets of the monitored components and the
maintenance windows' purpose; the ERP keeps the window records (ADR-0029).

| Service | Responsibility | Talks to | ADR |
|---|---|---|---|
| `provisioner` | Builds the static AAS (AASX preload) before BaSyx starts | files | 0011, 0013 |
| `bridge` | Writes UNS telemetry into the AAS as configured by AIMC/AID (state and slow values only) | MQTT, AAS | 0015, 0019 |
| `historian` | Records the UNS telemetry of all devices (every FMI output) in InfluxDB 3 | MQTT, InfluxDB | 0019 |
| `influxdb3` | InfluxDB 3 Core 3.12.0: time-series database of the historian, port 8181, no auth, tmpfs | – | 0019 |
| `grafana` | Grafana 13.2.3: dashboards "LINE01 live" (historian) and "Alarms & events" (alarms database), port 3002; anonymous read-only, login (admin/editor) to edit; state in volume `vf_grafana-data` | InfluxDB (Flight SQL), TimescaleDB | 0022, 0026 |
| `mes` | Production execution: orders released by the ERP (ProductionOrder workers, confirmations), sessions, workpiece instance AAS and passports (retention), quality verdict, KLT contents, ISO 22400 KPIs; UNS event → BPMN message correlation (event topics from the AID) | MQTT, AAS, Operaton, ERP | 0016, 0020, 0025 |
| `sustainability` | Product carbon footprint per part (BPMN task `pcf-calculate`, energy from the historian, supplier footprints per component batch from the supplier batch AAS, data quality) written as the workpiece's CarbonFootprint submodel; OperationalCO2eq and LINE01 energy totals; sustainability KPIs, port 8097 | AAS (plant + supplier environment), Operaton, InfluxDB, MQTT (session) | 0019, 0025, 0028 |
| `erp` | ERP order simulator: production orders (B2MML-like), release via BPMN message `OrderReleased`, standing-order policy, confirmations, goods receipts from the suppliers' despatch advices / batch master data with supplier batch reference, status page; port 8098 | Operaton, supplier portal | 0025, 0028 |
| `supplier` | Supplier portal of the four component suppliers: despatch advices (ASN) per lot, publishes the batch AAS (BatchInformation, batch CarbonFootprint, material composition, certificate EN 10204 3.1) in the supplier environment; port 8190 | supplier AAS environment | 0028 |
| `supplier-aas-env` (+ `supplier-db`, `supplier-config`, `supplier-provisioner`) | Second BaSyx Go AAS environment 1.1.0 (own PostgreSQL, own preload from `aas/data/supplier`): supplier company AAS, supplier product types, batch AAS; port 8191, registry integration, no eventing | – | 0028 |
| `alarms` | ISA-18.2 alarm management of the PLC alarms and the advisory maintenance alarms (states, acknowledge, shelving, designed suppression), journal of all UNS events, alarm KPIs; REST port 8099 | MQTT, TimescaleDB | 0026 |
| `maintenance` | Predictive maintenance: health index and remaining useful life of the monitored components from the historian (`infra/maintenance.json`), results on the UNS and in ConditionMonitoring, observed Reliability, advisory alarm word; opens and executes `MaintenanceOrder` processes (ERP maintenance window, LineControl Maintain / SetUnitMode, MaintenanceRecord); REST port 8094 | InfluxDB, MQTT, AAS, Operaton, ERP | 0029 |
| `alarms-db` | TimescaleDB 2.30.2 (PostgreSQL 17): alarm journal, occurrences, states, UNS event journal; tmpfs, no host port | – | 0026 |
| `ops-gateway` | Executes the delegated LineControl operations (incl. Control Component skills and unit modes) as OPC UA method calls (PLC01) or UNS commands; endpoints resolved from Control Component → AID | AAS (delegation, configuration), OPC UA, MQTT | 0017, 0020, 0024 |
| `plc-comm` | Communication module of PLC01: OPC UA server `opc.tcp://localhost:4840/vf/plc01` (PackML structure after OPC 30050, engineered from the FMI model) fed by the simulated CPU (Godot) over the backplane port 4841 | Godot (backplane), OPC UA clients | 0024 |
| `edge` | Edge connector: subscribes the OPC UA servers described in the AIDs and publishes to the UNS; UNS commands → OPC UA method calls | AAS (AIDs), OPC UA, MQTT | 0024 |
| `dpp-api` | BaSyx Go DPP API 1.1.0: digital product passports (item: workpieces, model: PC3280_TYPE) read from the AAS database, port 8093 | PostgreSQL (shared with aas-env) | 0021 |
| `resolver` | GS1 Digital Link resolver, port 8096: `/01/<GTIN>[/21/<serial>]` → passport page (redirect), linkset (DPP, AAS, certificates), passport page en/de | AAS discovery/registry, DPP API | 0023 |
| `bpmn` | Operaton 2.1.5: process engine, Cockpit, Tasklist | – | 0016 |
| `nodered` (profile `sandbox`, optional) | Learner sandbox with example flows (UNS explorer, reject alarm, read the AAS, call an AAS operation); port 1880, no auth, outside the core data path; publishes only `{root}/sandbox/alert` | MQTT, AAS | – |

## Configuration (environment variables)

| Variable | Default | Used by |
|---|---|---|
| `VF_AAS_URL` | `http://localhost:8091` | bridge, mes, ops-gateway, sustainability |
| `VF_MQTT_URL` | `mqtt://localhost:1883` | bridge, mes, ops-gateway, sustainability, alarms |
| `VF_BPMN_URL` | `http://localhost:8092/engine-rest` | mes, sustainability, erp |
| `VF_AAS_PUBLIC_URL` | `http://localhost:8091` | all AAS clients: public prefix of descriptor endpoints, mapped to `VF_AAS_URL` unless `VF_AAS_ENDPOINT_MAP` is set |
| `VF_AAS_REGISTRIES` | `vf=$VF_AAS_URL` | bridge, mes, ops-gateway, resolver, sustainability: environments for discovery + registry (ADR-0023), `name=base[,name=base]` or JSON `[{name, discovery, aas_registry, submodel_registry}]`; first match wins, unreachable environments are skipped. Compose: sustainability `vf=http://aas-env:8091,supplier=http://supplier-aas-env:8191` (ADR-0028) |
| `VF_AAS_ENDPOINT_MAP` | `$VF_AAS_PUBLIC_URL=$VF_AAS_URL` | AAS clients: `public=reachable[,…]` prefix rewrites of descriptor endpoints (compose, sustainability: both `http://localhost:8091` and `http://localhost:8191`) |
| `VF_AAS_RESOLVER_TTL` | `300` | AAS clients: cache lifetime (s) of discovery/registry results (also dropped on BaSyx change events) |
| `VF_LINE_ASSET_ID` | `…/ids/asset/$VF_LINE` | ops-gateway: asset id whose AAS (discovery) holds `LineControl` |
| `VF_RESOLVER_PORT` / `VF_RESOLVER_PUBLIC_URL` | `8096` / `http://localhost:8096` | resolver: listen port, base of its own links |
| `VF_DPP_URL` / `VF_DPP_PUBLIC_URL` | `http://localhost:8093` | resolver: DPP API (compose: `http://dpp-api:8093`) and its public base for links |
| `VF_RETENTION` | `500` | mes: rolling window of workpiece AAS that are session data (units not shipped) |
| `VF_PASSPORT_LIMIT` | `0` | mes: maximum number of kept passports of shipped units (0 = unlimited, oldest removed first) |
| `VF_ERP_URL` | – (compose: `http://erp:8098`) | mes: order confirmations and line-side staging reports of new lots; empty = neither |
| `VF_SUPPLIER_URL` | – (compose: `http://supplier:8190`) | erp: supplier portal for despatch advices; empty = goods receipts without despatch advice |
| `VF_SUPPLIER_PORT` | `8190` | supplier: HTTP port (its `VF_AAS_URL` / `VF_AAS_PUBLIC_URL` = the supplier environment, `http://supplier-aas-env:8191` / `http://localhost:8191`) |
| `VF_SUSTAINABILITY_PORT` | `8097` | sustainability: HTTP port |
| `VF_ERP_PORT` / `VF_ERP_AUTO_RELEASE` / `VF_ERP_STANDING_QTY` / `VF_ERP_PLANNING_S` | `8098` / `true` / `48` / `5` | erp: HTTP port, standing-order policy, planning interval |
| `VF_MAINTENANCE_PORT` | `8094` | maintenance: HTTP port (also uses `VF_AAS_*`, `VF_MQTT_URL`, `VF_BPMN_URL`, `VF_INFLUX_URL` and `VF_ERP_URL` - compose `http://erp:8098` - for the maintenance windows) |
| `VF_ALARMS_PORT` / `VF_ALARMS_DB` | `8099` / `postgresql://vf_alarms:vf-local-only@localhost:5433/alarms` (compose: `alarms-db:5432`) | alarms: HTTP port, TimescaleDB |
| `VF_AAS_EVENTS_TOPIC` | `vf/basyx/submodelrepository/#` | bridge, mes, ops-gateway: BaSyx CloudEvents for reloads (empty = off) |
| `VF_BRIDGE_MIN_INTERVAL` | `5.0` | bridge: minimum seconds between writes of a numeric element |
| `VF_INFLUX_URL` | `http://localhost:8181` | historian, sustainability (compose: `http://influxdb3:8181`); database and batching in `infra/historian.json` |
| `VF_LINE` / `VF_OPS_PORT` | `LINE01` / `8095` | ops-gateway: line whose `LineControl` submodel is the entry of the resolution; HTTP port |
| `VF_OPCUA_ENDPOINTS` | – | ops-gateway, edge: rewrites AID OPC UA endpoints, `from=to[,from=to]` prefix replacements (compose: `opc.tcp://localhost:4840=opc.tcp://plc-comm:4840`) |
| `VF_PLC_INSTANCE` / `VF_OPCUA_BIND` / `VF_BACKPLANE_BIND` | `PLC01` / registry endpoint on `0.0.0.0` / `0.0.0.0:4841` | plc-comm: controller instance, OPC UA listen endpoint, backplane listen address |
| `VF_EDGE_PUBLISHING_MS` | `telemetry.min_interval_s` × 1000 (100) | edge: OPC UA subscription publishing interval |
| `VF_OIDC_TOKEN_URL` / `VF_OIDC_CLIENT_ID` / `VF_OIDC_CLIENT_SECRET` | – (secure profile: `http://keycloak:8080/realms/virtual-factory/protocol/openid-connect/token`, `vf-<service>`, `vf-<service>-local-secret`) | all AAS / HTTP clients: client-credential token (`vf_common.auth`), sent to BaSyx, DPP API, ERP, supplier portal; unset = no Authorization header |
| `VF_OIDC_ISSUER` / `VF_OIDC_JWKS_URL` / `VF_OIDC_AUDIENCE` | – (secure profile: `http://localhost:8180/realms/virtual-factory`, `http://keycloak:8080/…/certs`, `virtual-factory-api`) | erp, alarms, maintenance, sustainability, supplier, resolver, ops-gateway: bearer token check of their own endpoints (`vf_common.jwt_auth`); unset = open |
| `VF_MQTT_USER` / `VF_MQTT_PASSWORD` | – (secure profile: account per service, `infra/mosquitto/secure`) | all MQTT clients |
| `VF_BPMN_USER` / `VF_BPMN_PASSWORD` | – (secure profile: `mes`, `sustainability`, `maintenance`, `erp`) | BPMN clients: basic auth of the Operaton REST API |
| `VF_OPCUA_SECURITY` / `VF_OPCUA_USER` / `VF_OPCUA_PASSWORD` / `VF_OPCUA_USERS` / `VF_OPCUA_PKI_DIR` | `none` (secure profile: `sign_encrypt`) | plc-comm (server: `VF_OPCUA_USERS="name:password:operate\|read,…"`), edge, ops-gateway (client user token), `vf_common.opcua_security` |
| `VF_SECURITY_PROFILE` | `open` (secure profile: `secure`) | provisioner: security definitions written into the AID (OPC UA SignAndEncrypt/UserName, MQTT `basic_sc`) |
| `VF_RESOLVER_TOKEN_URL` | – | resolver: token endpoint named in the 401 login hint of restricted links |
| `VF_REPO` | repository root | all (asset data, templates, `uns.json`, `bpmn/`) |

## Secure profile (ADR-0027)

`docker compose -f infra/docker-compose.yml -f infra/docker-compose.secure.yml up -d --build` - same services,
authenticated ([security.md](../architecture/security.md) has the roles × resources matrix):

| Service | Outgoing (client) | Incoming (resource server) |
|---|---|---|
| bridge, mes, sustainability, maintenance, edge, ops-gateway, erp, supplier, resolver | client credentials `vf-<service>` (role `svc-<service>`), token cached, refreshed, one retry on 401 | – |
| erp, alarms, maintenance, sustainability, supplier | – | bearer token on every route except `/health` (401); write routes need a role (403): ERP orders/settings `planner`, confirmations/staging `svc-mes`, maintenance windows `planner`/`maintenance`/`svc-maintenance`; alarms ack/shelve `operator`/`maintenance` (the journal records the token's user); maintenance evaluate/settings `maintenance`/`planner`; supplier despatch advices `svc-erp` |
| ops-gateway | OPC UA user `ops-gateway` (operate) | delegated operations: BaSyx forwards the caller's token; roles `operator`, `planner`, `maintenance`, `svc-mes`, `svc-maintenance` |
| resolver | role `public` towards the DPP API | `linkType=vf:aas` / `vf:aasDescriptor` need a realm token (401 + `{"login": {"token_endpoint", "client_id": "vf-godot", …}}`) |
| aas-env, dpp-api, supplier-aas-env | – | BaSyx Go ABAC (`infra/basyx/security/*.rules.json`, trust list with `discoveryUrl`) |
| plc-comm | – | OPC UA Basic256Sha256 SignAndEncrypt, user names `edge`, `ops-gateway` (operate), `explorer` (read) |
| mqtt | – | accounts + ACL (`infra/mosquitto/secure/acl`), no anonymous access |
| bpmn | – | basic auth (users per service from `bpmn-users`, admin `demo`) |

Token for manual calls: `curl -s -d grant_type=password -d client_id=vf-godot -d username=operator1
-d password=virtualfactory http://localhost:8180/realms/virtual-factory/protocol/openid-connect/token`
(`access_token` → `Authorization: Bearer …`).

## bridge

- Loads every AIMC 2.0 submodel (`semanticId` filter) with `extent=withBlobValue`, resolves sources into the AID
  (topic = `forms.href`, JSON key = `properties.Value.key`) and sinks (submodel + idShort path, value type).
- Transformations: Lua `aimc_main(sources)` in a sandbox (state codes → `OperatingState`).
- Write policy: discrete values on change; numbers ≤ 1 per 5 s and element (a number that changed only once in
  5 s, e.g. a per-part measurement, is written at once), 0.2 % deadband; value-only PATCH.
- The AIMC maps only what the AAS stores (ADR-0019): discrete outputs, OperatingState/OperatingHours and the
  EnergyConsumption values - 104 mappings for 10 devices; continuous signals go only to the historian.
- Reloads on BaSyx events for AIMC/AID submodels and every 5 minutes.

## historian

- Subscribes to `{root}/session` (tag `session` from the birth message) and `{root}/+/+` (telemetry); devices and
  the FMI type of every output come from the asset data (`device.modelDescription`), unknown topics are ignored.
- Samples that arrive before the first session birth (the OPC UA edge publishes the PLC's initial values a moment
  before the factory announces its session) are held (max. 20 000) and written with that session once it is known -
  never with a placeholder session. Dashboards resolve "latest" to the session of the newest PLC01 row.
- Writes each sample with its UNS `ts` (simulation time base, ms precision) into database `vf`: one table per
  device (lower-case instance name = UNS segment, e.g. `cv01`), one field per FMI output (Float64 → float,
  Int32 → integer, Boolean → boolean, String → string), tag `session`. Samples of one tick share one row.
- Also subscribes to `{root}/maintenance/+/+` (results of the maintenance service, ADR-0029): table
  `maintenance`, tags `session` and `component` (e.g. `GR01`), field types from `maintenance.indicators` in
  uns.json (e.g. `SELECT time, health_index, rul_hours_low FROM maintenance WHERE component = 'GR01'`).
- Batches every 0.5 s or 1000 lines; InfluxDB unreachable → lines stay buffered (≤ 200 000, oldest dropped) and
  are retried with backoff 1 … 30 s; rejected lines (HTTP 4xx) are dropped and counted. Stats in the log every
  60 s. Configuration: `infra/historian.json`.
- Measured (real time, 10 devices, 107 variables): ~210 samples/s → ~90 rows/s (samples of one tick merged) in
  2 requests/s; a 240 s session gave 21 344 rows (RB01 5 455, CV01 3 657, AC01/LB01/LB02/QS01/SL01 ≈ 2 400 each,
  PLC01 123, KLTA01/KLTB01 8).

**Querying (host)** - InfluxDB 3 Core at `http://localhost:8181`, no token. Every device AAS has a TimeSeries
submodel whose `Segments/Historian` (LinkedSegment) holds `Endpoint` and `Query`; copy-paste test:

```bash
SM=$(printf %s 'https://virtual-factory.example/ids/sm/CV01/TimeSeries/1' | base64 | tr '+/' '-_' | tr -d '=')
SEG=$(curl -s "http://localhost:8091/submodels/$SM/submodel-elements/Segments.Historian/\$value")
curl -s -G "$(echo "$SEG" | jq -r .Endpoint)" --data-urlencode "q=$(echo "$SEG" | jq -r .Query)" | jq '.[-3:]'
```

`Endpoint` = `http://localhost:8181/api/v3/query_sql?db=vf&format=json`, `Query` e.g.
`SELECT "time", "belt_speed", "belt_position", "running", "power", "energy", "operating_hours", "fault" FROM
"cv01" WHERE time >= now() - INTERVAL '1 hour' ORDER BY time`. Rows are sparse (a field is set only in the rows
where it changed; JSON omits nulls). Further examples: `... WHERE session = 'S-…'` for one session,
`SELECT date_bin(INTERVAL '10 seconds', time) AS t, avg(power) FROM rb01 GROUP BY 1 ORDER BY 1` for aggregates,
POST `{"db": "vf", "q": "...", "format": "json"}` to `/api/v3/query_sql` as an alternative to GET.

## grafana

Grafana OSS 13.2.3 at `http://localhost:3002` (ADR-0022), configured from `infra/grafana/` (mounted read-only):

| File | Content |
|---|---|
| `grafana.ini` | anonymous Viewer in org "Virtual Factory", login form, no sign-up/telemetry/update checks/news, bundled plugins only (no download at start) |
| `provisioning/datasources/historian.yaml` | data source `Historian (InfluxDB 3)`, uid `vf-historian`: InfluxDB, query language SQL (Flight SQL over gRPC on `http://influxdb3:8181`, `insecureGrpc`, database `vf`, dummy token because InfluxDB runs `--without-auth`) |
| `provisioning/dashboards/virtual-factory.yaml` | file provider → folder "Virtual Factory", `allowUiUpdates: true`, rescan every 30 s |
| `dashboards/line01-live.json` | dashboard "LINE01 live", uid `vf-line01-live` (source of truth; panel list in the [user guide](../user-guide.md#dashboards-grafana)) |
| `provisioning/datasources/alarms.yaml` | data source `Alarms & events (TimescaleDB)`, uid `vf-alarms`: built-in PostgreSQL (`grafana-postgresql-datasource`, TimescaleDB mode) on `alarms-db:5432`, database `alarms`, read-only role `grafana` |
| `dashboards/maintenance.json` | dashboard "Maintenance", uid `vf-maintenance` (ADR-0029): health index, RUL (hours, grips, lower bound), health state, open maintenance order, finger wear vs. limit, grip force / closing time, regrips, maintenance alarms 901/202 from the alarm journal; [user guide](../user-guide.md#predictive-maintenance) |
| `dashboards/alarms-events.json` | dashboard "Alarms & events", uid `vf-alarms-events` (ISA-18.2 / EEMUA 191 KPIs, current alarms, journals; [user guide](../user-guide.md#alarms-and-events)) |
| `entrypoint.sh` | starts Grafana, then (HTTP API, idempotent) renames org 1, creates user `editor` (role Editor), sets the home dashboard |

- Accounts: `admin` (`GF_SECURITY_ADMIN_PASSWORD`, compose) and `editor` (`VF_GRAFANA_EDITOR_PASSWORD`), local
  default `virtualfactory` (O34). Passwords apply when the volume `vf_grafana-data` is created.
- Edits saved in the UI and new dashboards persist in `vf_grafana-data`; a changed JSON file in the repository
  replaces the saved version of the provisioned dashboard at the next rescan. Reset everything:
  `docker compose -f infra/docker-compose.yml rm -sf grafana && docker volume rm vf_grafana-data`.
- Query from scripts like a panel (anonymous works as viewer): `POST /api/ds/query` with
  `{"from": "now-15m", "to": "now", "queries": [{"refId": "A", "datasource": {"uid": "vf-historian"},
  "rawSql": "SELECT time, power FROM rb01 WHERE $__timeFilter(time)", "format": "table"}]}`.
- Integration test: `tools/tests/test_grafana_integration.py` (health, anonymous read/refused save, admin save,
  editor role, data source health, a panel query).

## mes

**Workpiece instance AAS** (`aas/data/blueprints/workpiece_instance.yaml`, built with the provisioner's
`BuildContext` together with the product type, strictly validated before upload):

| Stage (BPMN task) | Trigger | Content |
|---|---|---|
| released (`workpiece-create`) | `part_released` | Nameplate, DppMetadata, ExecutedProcesses OP10–OP70 (cell test data, component lots), ContactInformations, HierarchicalStructures (as-built BoM with batches), ProductMaterialComposition, ProductCircularity (recycled content per lot), AssetLocation (CV01); sets `orderId` (running production order) |
| inspected (`workpiece-record-inspection`) | `part_inspected` | + OP75/OP80, QualityInspection (verdict vs. recipe limits), MeasurementValue ×2, TechnicalData (as-built) |
| packed (`workpiece-record-packing`) | `part_sorted` | + OP90, run completed, HandoverDocumentation (good parts: inspection certificate PDF; type documents - uploaded as attachments), AssetLocation (KLT, slot), KLT contents; passport `Active` for a good part. The CarbonFootprint follows in the next task (`pcf-calculate`, sustainability service) |
| lost (`workpiece-mark-lost`) | 5 min timeout | run aborted, passport `Inactive` |

**Line-side staging (ADR-0028)**: `workpiece-create` also reports every lot seen for the first time to the ERP
(`POST {VF_ERP_URL}/api/material-staging {"material", "lot"}`, background thread; repeated with the next part from
the lot after a failure) - the ERP posts the goods receipt from the supplier's despatch advice, which publishes the
batch AAS. Purchased batch nodes of the as-built BoM carry the batch Digital Link as globalAssetId (SelfManaged,
[aas-model.md §6b](aas-model.md#6b-item-level-digital-product-passport-adr-0021)).

Each workpiece AAS is the item-level passport of its part (ADR-0021, [aas-model.md §6b](aas-model.md#6b-item-level-digital-product-passport-adr-0021)):
DPP id = AAS id, globalAssetId = `uniqueProductIdentifier` = GS1 Digital Link, `contentSpecificationIds` = the
passport submodels at the stage (at packing including the CarbonFootprint provided by the sustainability
service), `dppStatus` `Inactive` while in production and for rejects/lost parts, `Active` for shipped (packed good)
parts.

**Retention (ADR-0025, LINE01/DataRetentionPolicies)**: a new session birth (Godot start) or an MES start removes the
workpiece AAS that are session data - units in production, rejects, lost units - and their WorkpieceLifecycle
instances; passports of shipped units (`dppStatus` Active, found with one query over all DppMetadata submodels)
are kept and stay readable through the DPP API. Session data is a rolling window of `VF_RETENTION`; shipped
passports are unlimited unless `VF_PASSPORT_LIMIT` is set. Submodels of other services (CarbonFootprint) stay
referenced when the MES replaces the shell and are deleted with it. Serial numbers are retentive in live sessions
(Godot `user://retain.json`); a stage that would overwrite the passport of a shipped unit of an earlier session
(reused serial) fails with an incident instead.

- Component lots come from the assembly cell (`part_released.lots` = FMI output `last_lots`, `lots.py`); each
  feeder changes its lot after its own number of parts. Without `lots` (older simulation builds) the blueprint
  lots are shifted every 250 parts. Values the simulation does not produce (torques, forces, grease) are derived
  deterministically per serial around the recipe values (`cell_data.py`).
- Inspection certificate (`certificate.py`, `pdf.py`): one A4 page, ~7 KB, for packed good parts; uploaded with the
  type documents as File attachments of HandoverDocumentation (BaSyx stores identical files once).
- Verdict: leak rate and stroke time (cell) and ΔE*ab (QS01) against the formula limits of the master recipe; the
  PLC sorts by colour only, so a part with a failed cell test packed into KLT A raises the "mis-sorted" user task.
- KLT contents: `HierarchicalStructures` of KLTA01/KLTB01, station → `Box` → one Node + HasPart per part; cleared on
  `container_exchanged`.
- Every 15 s: ISO 22400 KPI elements of LINE01 from the PackML state durations and counters (energy and CO₂e values:
  sustainability service).
- Orders (`orders.py`): the order started by `line-start` is the active order; released workpieces carry its number
  (`orderId`, inspection certificate) and their component lots are booked to it. Confirmations to the ERP
  (`POST {VF_ERP_URL}/api/production-performance`, B2MML-like OperationsPerformance): InProcess at start and when
  the progress changes (best effort), Completed in `order-confirm` with MaterialProducedActual (good, scrap) and
  MaterialConsumedActual (article, lot, parts × BulkCount). A PLC counter restart (new session) keeps the order's
  progress (baseline rebased). Order tasks retry every 15 s for an hour (line/ERP unavailable) before an incident.

### External-task topics

| Topic | Process | Effect |
|---|---|---|
| `workpiece-create`, `workpiece-record-inspection`, `workpiece-record-packing`, `workpiece-mark-lost` | WorkpieceLifecycle | see table above; sets `orderId`, `verdict`, `plannedContainer`, `correctContainer` |
| `pcf-calculate` (sustainability service) | WorkpieceLifecycle | after packing: CarbonFootprint submodel of the part; sets `pcf`, `pcfMethod` |
| `line-start` | ProductionOrder | SetAutoExchange(!manual), Clear/Reset/Start as needed, counter baseline |
| `order-progress` | ProductionOrder | reads `parts_ok`/`parts_nok` from PLC01/OperationalData; `orderDone`, `rejectAlarm` (≥ 10 parts in window and rate > limit) |
| `line-command` | ProductionOrder | ExecutePackMLCommand(`packmlCommand` input parameter) |
| `line-exchange-container` | ProductionOrder | ExchangeContainer(`container`) |
| `order-close` | ProductionOrder | SetAutoExchange(true), summary |
| `order-confirm` | ProductionOrder | final confirmation to the ERP (good, scrap, consumed lots); `erpConfirmed` (false for orders the ERP does not know) |

**Messages**: `PartReleased` (starts WorkpieceLifecycle, business key = serial), `PartInspected`, `PartSorted`
(correlated by serial, retried for 60 s), `ContainerFull` (all waiting ProductionOrder instances); `OrderReleased`
(sent by the ERP, starts ProductionOrder, business key = order number).

**Event discovery (ADR-0020)**: the MES subscribes to the topics of all AID event affordances on the AAS server
(`InteractionMetadata.events.<name>.forms.href` of every AssetInterfacesDescription) and maps the affordance name
(`part_released`, `part_inspected`, `part_sorted`, `container_full`, `container_exchanged`) to the messages above;
messages on topics the AAS does not describe are ignored. Reloaded (debounced 2 s) on BaSyx change events of AID
submodels and every 5 min; if discovery fails or finds no events, the previous topics are kept and an error is
logged (no fallback to `uns.json`). Still taken from the UNS registry: the session birth `{root}/session` (a
namespace topic of the Godot gateway, not an asset affordance) and the PLC01 KPI telemetry topics.

## sustainability

Owns the product carbon footprint (ADR-0025). Port 8097.

- **BPMN task `pcf-calculate`** (WorkpieceLifecycle, after `workpiece-record-packing`): production-based PCF of the
  part (method [aas-model.md §6a](aas-model.md#6a-runtime-submodels-m4)) - purchased components (A1) + energy of the
  part's assembly-cell cycle and its residence-time share of the downstream devices + compressed air from the
  historian, × emission factor of LINE01, + allocated production losses (A3). Written as the workpiece's
  **CarbonFootprint** submodel (three entries: A1-A3 total, A1, A3 with ElectricalEnergy, CompressedAirEnergy,
  ProductionLossCO2eq, LineResidenceTime), built from the blueprint section, strictly validated, referenced from the
  shell the MES created. Idempotent per serial (retries reuse the footprint, losses are allocated once). Sets `pcf`,
  `pcfMethod` (`historian` | `fallback`: line energy per part, rolling 5 min, when the historian is unavailable).
- **Supplier footprints** (`suppliers.py`, `supplier_batches.py`): `SupplierFootprints.footprint(bom_line, batch)
  -> ComponentFootprint` per BoM node of PC3280_TYPE and the batch built into the part (`part_released.lots`).
  `ChainedFootprints(SupplierBatchFootprints, ComponentTypeFootprints)`: first the CarbonFootprint of the
  **supplier batch AAS** (GTIN of the component type AAS from its registry descriptor + lot → batch Digital Link →
  federated discovery over `VF_AAS_REGISTRIES`; cached per batch, unknown batches asked again after 30 s), else
  the CarbonFootprint of the component type AAS (same for every batch). Per component the part records `source`
  (`supplier-batch` | `component-type-aas`), `dataQuality` (`primary` | `secondary`), the supplier's
  `primaryShare` and the batch `assetId`; the CarbonFootprint gets `PrimaryDataShare` (entries A1-A3 and A1) and
  `SupplierSpecificDataShare` (A1) ([aas-model.md §6a](aas-model.md#6a-runtime-submodels-m4) item 8).
- Every 10 s: `OperationalCO2eq`/`LastUpdate` per device and the line totals in LINE01/EnergyConsumption;
  `MeasurementStart` at each session birth.
- `GET /health`, `GET /api/kpis` (session: good/rejected parts, average PCF of a good part with A1/A3, energy per
  good part, production losses, loss share of A3, `avgPrimaryDataShare`, `avgSupplierSpecificShareA1`, line
  energy/CO₂e since session start), `GET /api/footprints` (newest first, `?limit=`), `GET /api/footprints/{serial}`
  (incl. components with batch, source and data quality, `primaryDataShare`, `supplierSpecificShareA1`).

## erp

ERP order simulator (ADR-0025), port 8098, status page `http://localhost:8098/`. State in memory (like the engine).

| Endpoint | Function |
|---|---|
| `GET /api/materials` | material master from the asset data: PC3280 and the 9 components (article = customerPartId, supplier, BoM node and quantity) |
| `GET /api/orders[?state=]`, `GET /api/orders/{id}` | production orders as OperationsRequest-like JSON (`RequestState` Created → Released → InProcess → Completed / Aborted, `Progress` with good, scrap, confirmations, consumed lots) |
| `POST /api/orders` | `{"quantity", "material"?, "dueDate"?, "release"?}` → `PO-<year>-<seq>` (Created, queued) |
| `POST /api/orders/{id}/release` | BPMN message `OrderReleased` (business key = order number) → ProductionOrder; 409 while another order is open (one order per line), 503 if the process is not deployed |
| `POST /api/production-performance` | confirmation of the MES (OperationsPerformance: `OperationsResponse.OperationsRequestID`, `ResponseState`, `SegmentResponse.MaterialProducedActual` / `MaterialConsumedActual`); 404 for unknown orders |
| `GET /api/batches`, `POST /api/goods-receipts` | component batches (received, consumed, stock, source `despatch-advice`, `goods-receipt` or `consumption` for a retroactive receipt from the backflush, `SupplierBatch`: despatch advice number/date, batch Digital Link, AAS id, shell link, material certificate link, batch PCF and primary data share - null for in-house lots) / goods receipt `{"material", "lot", "quantity"?}` (quantity defaults to the despatch advice) |
| `POST /api/material-staging` | `{"material", "lot"}` from the MES: first staging of a lot at the line (ship-to-line) → despatch advice from the supplier portal → goods receipt (201; 200 if already received, or `Status` `in-house` / `no despatch advice`); 503 if the portal is unreachable (the MES reports again) |
| `GET/PUT /api/settings` | `autoRelease`, `standingQuantity`, `rejectRateLimit`, `manualContainerExchange` |
| `GET/POST /api/maintenance-windows`, `GET .../{id}`, `POST .../{id}/complete`, `POST .../{id}/cancel` | maintenance windows (ADR-0029): `{"maintenanceOrder", "start": "OrderBoundary" \| "Immediate", "reason"}` → `MW-<seq>` (idempotent per maintenance order); states Requested → Active (no order open, or at once for Immediate; `InterruptedOrder` = order running then) → Completed / Cancelled. While a window is open no order is released (release → 409) |

Planning loop (every `VF_ERP_PLANNING_S`): adopt ProductionOrder instances the MES runs but the ERP does not know
(after an ERP restart), abort open orders without a running instance (engine restart), and - with auto release -
release the oldest Created order or a standing order of `standingQuantity` parts when nothing is open. The line
stops at the end of an order (ProductionOrder) and restarts with the next release.

```bash
curl -s -X POST localhost:8098/api/orders -H 'Content-Type: application/json' -d '{"quantity": 12, "dueDate": "2026-10-06"}'
curl -s localhost:8098/api/orders | jq '.[] | {ID, RequestState, Progress: .Progress | {Good, Scrap}}'
curl -s localhost:8098/api/batches | jq '.[] | {MaterialLotID, Supplier, Consumed, Source, Batch: .SupplierBatch.GlobalAssetId}'
```

## supplier

Supplier portal (ADR-0028), port 8190, in front of the **supplier AAS environment** (port 8191, own database and
preload `infra/basyx/preload-supplier` built by `provisioner build --data supplier`). It stands for the shipping
systems of Druckguss Pfalz, Dichtungstechnik Süd, Normteile Rhein-Neckar and Kunststofftechnik Westrich.

| Endpoint | Function |
|---|---|
| `GET /health` | status, number of despatch advices issued in this run |
| `GET /api/articles` | the five supplier articles: product type tag, manufacturer / customer part id, GTIN, supplier, lot format |
| `POST /api/despatch-advices` | `{"article": customer or supplier part id, "batch": lot}` → despatch advice (DESADV-like JSON: number `DA-<lot>`, date, supplier/buyer with GLN, line with GTIN, batch, quantity, production date, `BatchAsset` with Digital Link, AAS id, shell link, certificate link, batch PCF); publishes the batch AAS on the first request (idempotent); 404 for lots not in the supplier's format (e.g. in-house lots), 503 if the supplier environment is down |
| `GET /api/despatch-advices` | despatch advices issued in this run |

Batch AAS: [aas-model.md §6c](aas-model.md#6c-supplier-batch-aas-adr-0028); values per lot are deterministic
(`aas/data/supplier/batch_profiles.yaml`). Read a batch through the federation by its Digital Link:

```bash
SUP=http://localhost:8191
curl -s -X POST localhost:8190/api/despatch-advices -d '{"article": "5032-1009", "batch": "KTW-26-0911"}' | jq .BatchAsset
DL="https://virtual-factory.example/01/04099994010016/10/KTW-26-0911"
ID=$(curl -s "$SUP/lookup/shells?assetIds=$(link globalAssetId "$DL")" | jq -r '.result[0]')   # helpers: see below
curl -s "$SUP/lookup/shells?assetIds=$(link gtin 04099994010016)"   # supplier type (the plant: 8091 -> CMP_*)
```

## alarms

ISA-18.2 alarm management and UNS event journal (ADR-0026), port 8099, database `alarms-db` (TimescaleDB).

- **Inputs** (UNS registry): `{root}/plc01/active_alarms` (alarm word: all active PLC alarms, e.g. `100,201`;
  `alarm_code` as fallback until it arrives), `{root}/maintenance/active_alarms` (advisory alarm word of the maintenance
  service, source MAINTENANCE, merged with the PLC alarms; ADR-0029), `{root}/plc01/packml_state`, session/status,
  `{root}/+/event/+`, `{root}/+/cmd/+`, `{root}/+/cmd-resp/+`.
- **Master alarm database** `infra/alarms.json`: per code texts en/de, priority (Critical/High/Medium/Low), class,
  PLC reaction, response time, consequence, remedy, `suppressed_by` (consequential alarms, e.g. 201 while the E-stop
  100 is active) and `suppress_in_states` (e.g. 401 while STOPPED/ABORTED); shelving maximum 8 h; stale after 1 h;
  chattering ≥ 3 activations in 60 s; flood > 10 per 10 min.
- **States** per alarm: NORM, UNACK, ACKED, RTNUN, SHLVD, DSUPR (journal events ACTIVATED, CLEARED, ACKNOWLEDGED,
  SHELVED, UNSHELVED, SHELVE_EXPIRED, SUPPRESSED, UNSUPPRESSED). Restored from the database at restart.

| Endpoint | Function |
|---|---|
| `GET /api/alarms[?all=true]`, `GET /api/alarms/{code}` | current alarms (not NORM, most urgent first) with state, priority, texts, remedy, times, operator |
| `POST /api/alarms/{code}/ack`, `POST /api/alarms/ack` | acknowledge one / all unacknowledged - `{"operator", "comment"?}` (operator mandatory) |
| `POST /api/alarms/{code}/shelve`, `.../unshelve` | `{"durationS", "operator", "comment"?}` (1 s … 8 h) / `{"operator"}` |
| `GET /api/journal` | alarm transitions `?since&until&code&event&limit` (default last 24 h, 200 rows) |
| `GET /api/events` | UNS event journal `?since&until&kind&name&device&limit` (kind: event, command, ack, state, session, status) |
| `GET /api/kpis[?window=60]` | annunciated alarms per 10 min (average, peak), flood period share, standing/stale/shelved/suppressed/unacknowledged, top 10 bad actors with share, chattering, priority distribution, mean time to acknowledge/clear |
| `GET /api/definitions` | master alarm database |

**Schema** (`services/alarms/src/alarms/schema.sql`, created at start): hypertables `alarm_journal` (time, code,
event, state, priority, annunciated, operator, comment, session, occurrence_id; retention 90 days) and
`event_journal` (time, kind, device, name, topic, session, seq, source_time, payload jsonb; retention 30 days);
tables `alarm_definition`, `alarm_state` (one row per alarm, updated in place), `alarm_occurrence` (one row per
activation: activated/acknowledged/cleared, annunciated). Read-only role `grafana`. psql:
`docker compose -f infra/docker-compose.yml exec alarms-db psql -U vf_alarms alarms`.

```bash
curl -s localhost:8099/api/alarms | jq '.[] | {code, state, priority, text: .text.en}'
curl -s -X POST localhost:8099/api/alarms/201/ack -H 'Content-Type: application/json' -d '{"operator": "trainer"}'
curl -s 'localhost:8099/api/kpis?window=60' | jq '{ratePer10Min, standing, badActors}'
```

## maintenance

Condition monitoring and predictive maintenance (ADR-0029), port 8094, configuration `infra/maintenance.json`
(monitored components: device, indicator, limit, cycle counter, symptoms, fault output, Reliability set,
maintenance task, confirmation parameter of the skill Maintain, advisory alarm; order policy).

- **Every 10 s per component**: history from the historian (`SELECT time, grip_cycles, finger_wear, … FROM rb01
  WHERE session = … ORDER BY time DESC LIMIT 200`, cut at the last part change) → health index
  `1 - wear/limit`; RUL = least-squares line of the indicator over the cycles since the part change, 90 % lower
  bound, hours at the throughput of the last 20 samples, predicted failure date, confidence; without a
  significant trend (n < 6 or t < 3) the design rate from Reliability (useful life, lower bound B10). Health
  state Good / Warning / Alarm / Unknown, recommendation en/de.
- **Order policy** (`/api/settings`): open a `MaintenanceOrder` when the RUL lower bound < `rulHoursThreshold`
  (8 h) while HI < `healthIndexGate` (0.85), or HI < `healthIndexOrder` (0.25), or the device reports its fault
  output; one open order per component; advisory alarm (901) in the alarm word while it is open.
- **Outputs**: UNS `{root}/maintenance/{component}/{health_index | wear | rul_cycles | rul_cycles_low | rul_hours |
  rul_hours_low | confidence | throughput | health_state | order}` (retained, `ts` = time of the latest sample)
  and `{root}/maintenance/active_alarms`; historian table `maintenance` (tags session, component); AAS
  `ConditionMonitoring` (changed values only), MaintenanceRecords and the Reliability set `…Observed` after an
  order ([aas-model.md §6d](aas-model.md#6d-predictive-maintenance-adr-0029)).
- **BPMN worker** (external tasks of `bpmn/maintenance_order.bpmn`, retried every 15 s up to 40 times):
  `maintenance-reserve` (ERP window, start from the planner's `immediate`), `maintenance-check-line` (window
  active → `lineFree`), `maintenance-line-stop` (`ExecuteSkill(Maintain, Maintenance)`), `maintenance-device-reset`
  (`ExecuteSkill(Maintain, Maintenance, {"gripper_maintenance_reset": true})`, waits for `grip_cycles` = 0 on the
  UNS; skipped when `partsReplaced` is false), `maintenance-line-handback` (`SetUnitMode(Production)`, window
  completed, interrupted order restarted with `ExecuteSkill(Produce, Production)`), `maintenance-record`.
  Running orders are adopted at start.

| Endpoint | Function |
|---|---|
| `GET /health` | status, session, components, open orders, alarm word |
| `GET /api/components`, `GET /api/components/{tag}` | condition per component: health state, prognosis (HI, value, cycles, RUL cycles/hours with lower bounds, failure time, confidence, method, points, throughput, rate), open order, symptoms, fault |
| `POST /api/components/{tag}/evaluate` | evaluate now |
| `GET /api/orders` | open maintenance orders `{component: order}` |
| `GET/PUT /api/settings` | order policy `{"rulHoursThreshold", "healthIndexGate", "healthIndexOrder"}` |

```bash
curl -s localhost:8094/api/components/GR01 | jq '{healthState, order, p: .prognosis | {healthIndex, rulCyclesLow, rulHoursLow, method}}'
curl -s -X PUT localhost:8094/api/settings -d '{"rulHoursThreshold": 24}'
```

## dpp-api

BaSyx Go DPP API (`eclipsebasyx/dppapi-go:1.1.0`, ADR-0021) at `http://localhost:8093` (Swagger UI `/swagger`,
health `/health`). It reads the passports directly from the AAS database (same PostgreSQL as aas-env); the MES
writes them as workpiece AAS through the AAS API (the CarbonFootprint section: sustainability service). Passports of
shipped parts stay readable after new sessions (retention, ADR-0025). Id-based reads need AAS id = `digitalProductPassportId`
(BaSyx limitation) - fulfilled by design. Attachment links point to the AAS environment
(`GENERAL_EXTERNALURL=http://localhost:8091`). History endpoints (`/v1/dppsByIdAndDate`) are not configured (O40).

```bash
DPP=http://localhost:8093
enc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
SERIAL=PC3280-2026-000005      # any produced part, e.g. from the inspector or the KLT contents
# by DPP id (= AAS id of the workpiece)
curl -s "$DPP/v1/dpps/$(enc "https://virtual-factory.example/ids/aas/WP_${SERIAL//-/_}")" | jq 'keys'
# by product id (= GS1 Digital Link = globalAssetId)
curl -s "$DPP/v1/dppsByProductId/$(enc "https://virtual-factory.example/01/04099999032808/21/$SERIAL")" \
  | jq '{digitalProductPassportId, granularity, dppStatus, contentSpecificationIds}'
# one element: path = $['<semantic id of the content section>']['<idShort>']...
curl -s "$DPP/v1/dpps/$(enc "https://virtual-factory.example/ids/aas/WP_${SERIAL//-/_}")/elements/$(enc \
  "\$['https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0']['ProductCarbonFootprints'][0]['PcfCO2eq']")"
# the model-level passport of the product type, also in the full representation (types and metadata)
curl -s "$DPP/v1/dppsByProductId/$(enc https://virtual-factory.example/01/04099999032808)" | jq .granularity
curl -s "$DPP/v1/dpps/$(enc https://virtual-factory.example/ids/aas/PC3280_TYPE)?representation=full" | jq '.elements | length'
```

Content sections are keyed by semantic id (`https://admin-shell.io/idta/nameplate/3/0/Nameplate`,
`0173-1#01-AHX837#002` TechnicalData, `0173-1#01-AHF578#003` HandoverDocumentation, ...). File elements are
rendered as attachment URLs, e.g. the certificate:
`jq -r '.["0173-1#01-AHF578#003"].Documents[0].DocumentVersions[0].DigitalFiles[0]'`. The BaSyx web UI (3001)
has no DPP view; it shows the same AAS/submodels from the AAS environment. `representation=full` fails for item
passports (HTTP 422 `DPP-ELEM-FULL-UNSUPPORTED`): DPP API 1.1.0 converts only Property, MLP, SMC, SML, Entity and
File, while the BoM (HasPart/SameAs relationships) and QualityInspection (references) contain other element types -
use the default compressed representation (O38).

### Traceability: which parts contain a batch?

The as-built BoM of every workpiece (HierarchicalStructures, node statement `BatchId`) answers it with the AAS
API alone - all submodels with the HierarchicalStructures semantic id, filtered by batch:

```bash
LOT=L2609-0418                 # barrel lot of serials 1-35 of a session
HS=$(printf %s '{"type":"ModelReference","keys":[{"type":"Submodel","value":"https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"}]}' \
  | base64 | tr '+/' '-_' | tr -d '=')
curl -s "http://localhost:8091/submodels?semanticId=$HS&limit=1000" | jq -r --arg lot "$LOT" '.result[]
  | select(.id | contains("/sm/WP_")) | . as $sm | .submodelElements[] | select(.idShort == "EntryNode")
  | .statements[]? | select(.modelType == "Entity") as $node | $node.statements[]?
  | select(.idShort == "BatchId" and .value == $lot) | "\($sm.id | split("/")[5]) \($node.idShort)"'
```

prints e.g. `WP_PC3280_2026_000001 Barrel` per affected part (AAS tag = `WP_<serial>`; the HS template's semanticId is
a ModelReference with key type Submodel, BaSyx matches the reference type); the passport of each is then one DPP
API call. Lot changes per feeder: [aas-model.md §6b](aas-model.md#6b-item-level-digital-product-passport-adr-0021).

## ops-gateway

`POST /operations/{ExecutePackMLCommand|SetUnitMode|ExchangeContainer|SetAutoExchange|ExecuteSkill}` with the
OperationVariable array sent by BaSyx; returns the output variables (`Accepted`, `State` for
ExecutePackMLCommand/SetUnitMode/ExecuteSkill, `Message`). PackML commands are checked against the state model before
they are sent and confirmed by the resulting state. Timeouts: 3 s acknowledgement / OPC UA call, 10 s state.

**Transport per endpoint (ADR-0024).** An endpoint whose AID affordance is in an interface with an `opc.tcp://`
base is executed over OPC UA: actions are method calls (`href` = method, called on its parent object, argument
typed from the method's InputArguments; Good = accepted, a bad status code is the rejection reason, e.g.
`BadNotConnected` when the simulation is not linked to plc-comm), properties are monitored items (publishing
interval 50 ms, queue 50, so transient states such as IDLE after Reset are seen). Affordances of MQTT interfaces
use the command/ack topics below. PLC01's endpoints are OPC UA except `GripperMaintenanceReset` (an action of
robot RB01's MQTT interface, ADR-0029); the asyncua client reconnects by itself.

**Configuration from the AAS (ADR-0020).** Nothing about topics is configured in the gateway or read from
`uns.json`:

```text
LINE01/LineControl.ControlComponent ──► PLC01/ControlComponentInstance
    Endpoints.PackMLState     ──EndpointReference──► AID properties.packml_state  (OPC UA: href = node;
    Endpoints.UnitMode        ───────────────────► AID properties.unit_mode         MQTT: topic, value key v)
    Endpoints.PackMLCommand   ──EndpointReference──► AID actions.packml_command    ┐ OPC UA: href = method, base
    Endpoints.UnitModeCommand ───────────────────► AID actions.unit_mode_command  │ MQTT: forms (topic, QoS, op),
    Endpoints.ContainerExchange ─────────────────► AID actions.klt_exchange_command │ input keys v / corr / source,
    Endpoints.AutoExchange    ───────────────────► AID actions.auto_exchange       ┘ ackForms + output (ack)
    Endpoints.GripperMaintenanceReset ──► RB01/AID (MQTT) actions.gripper_maintenance_reset
    Skills.<name>: Disabled, Modes, Parameters, UsesEndpoints → Endpoints.<name>
```

- Resolved at start-up (retry every 5 s while the AAS server is unreachable or still importing; operations are
  rejected with "not configured" until then - deliberately **no fallback to uns.json**). Resolved again on BaSyx
  change events for the submodels it was read from (LineControl, CC instance, AID; debounced 1 s) and every 5 min.
  A failed reload keeps the last good configuration.
- The log lists every endpoint with topic, QoS, retain, value key and ack topic, and every skill; `GET /health`
  returns the same (`status` = `ok` | `unconfigured`).

**ExecuteSkill(Skill, Mode, Parameters)** executes a skill of the Control Component Instance:

| Skill | Effect | Parameters (`Parameters` = JSON object) |
|---|---|---|
| `Produce` | Clear / Reset / Start / Unhold / Unsuspend until EXECUTE (waits 2 s for the PLC's auto start after Reset); `State` = EXECUTE | `auto_exchange` (sent first via the endpoint whose AID action has that name); `belt_speed`, `klt_capacity` are rejected (no runtime endpoint); outputs (`parts_*`) are rejected |
| `ExchangeContainer` | KLT exchange command via the skill's endpoint `ContainerExchange` | `container` (required; 1 or 2 as enumerated in the skill's `Values`) |
| `Maintain` (mode Maintenance) | Stop (unless STOPPED/IDLE/ABORTED), unit mode Maintenance; then the confirmation parameters - only while stopped in Maintenance; `State` = STOPPED (ADR-0029) | `gripper_maintenance_reset` (`true` = fingers of GR01 replaced → AID action of RB01 via the endpoint `GripperMaintenanceReset`; `false` = nothing sent) |

- Checks before anything is sent: skill exists and is not `Disabled`; `Mode` is one of the skill's `Modes` (empty
  = first mode); parameter names, Direction In, type, Min/Max and enumerated values from the skill description.
- **Unit mode:** with the endpoints `UnitMode`/`UnitModeCommand` the mode is applied before the skill runs
  (Production 1, Maintenance 2, Manual 3 via `unit_mode_command`, confirmed by `unit_mode` within 2 s). The PLC
  changes the mode only in STOPPED, IDLE or ABORTED; otherwise the skill is rejected with "stop the line first".
  Maintenance/Manual: no auto start, no infeed from AC01 (the line runs empty) - the hook for maintenance runs.
- `ExchangeContainer(Container)` is a shortcut for the skill `ExchangeContainer` (same validation).
- `SetUnitMode(Mode)` (LineControl 1.2, OPC 30050 SetUnitMode): only the unit mode change (Production,
  Maintenance, Manual), same rules; used to hand the line back to production after a maintenance order.

```bash
curl -X POST -H 'Content-Type: application/json' "http://localhost:8091/submodels/$(printf %s 'https://virtual-factory.example/ids/sm/LINE01/LineControl/1' | base64 | tr '+/' '-_' | tr -d '=')/submodel-elements/ExecuteSkill/invoke" -d '{"inputArguments":[{"value":{"modelType":"Property","idShort":"Skill","valueType":"xs:string","value":"Produce"}},{"value":{"modelType":"Property","idShort":"Mode","valueType":"xs:string","value":"Production"}},{"value":{"modelType":"Property","idShort":"Parameters","valueType":"xs:string","value":"{\"auto_exchange\": true}"}}],"clientTimeoutDuration":"PT30S"}'
```

## plc-comm

The communication module of PLC01 (ADR-0024): one process with the OPC UA server (asyncua 2.0.1,
`opc.tcp://0.0.0.0:4840/vf/plc01`, security None / Anonymous; secure profile: only Basic256Sha256 SignAndEncrypt with
user name tokens from `VF_OPCUA_USERS`, method calls for `operate` accounts - ADR-0027, O57) and the backplane server
(TCP 4841) for the simulated CPU in Godot. The address space is built at start-up from the FMI model description of
PLC01 (asset data) and `opcua.servers.PLC01` in `godot/config/uns.json`; node list in
[uns.md](uns.md#opc-ua-path-plc01).

- One CPU at a time (a new connection replaces the old one). Every image message updates the changed nodes with the
  CPU's timestamp; without CPU all process values are BadNoCommunication and `Diagnostics.CpuConnected` is false.
- Method call → `write` on the backplane → CPU applies it between two master steps → `result` → status code
  (timeout 2 s: BadTimeout).
- Log line every 60 s: images/s, events, writes and their mean latency. `plc_comm.testing.FakeCpu` is a scripted
  CPU for tests.

## edge

The edge connector (ADR-0024) reads every AID that has an OPC UA and an MQTT interface (today PLC01; found through
the submodel registry like the other services, `RegistryAas`, ADR-0023) and bridges them affordance by
affordance (pairing by name). Secure profile: OPC UA Basic256Sha256 SignAndEncrypt as user `edge`, broker account
`edge` (writes only PLC01 telemetry, events and acks):

| OPC UA (southbound) | UNS (northbound) |
|---|---|
| monitored item of each property (sampling 0, queue 50, publishing 100 ms) | `{root}/plc01/<variable>` `{"v","ts"=SourceTimestamp}`, retained, QoS 0 |
| events of `PartInspectedEventType` / `PartSortedEventType` on `PLC01` | `{root}/plc01/event/<event>` (`event`, `device`, `session`, `seq`, `ts`, fields), QoS 1 |
| method `Commands/<variable>(Value)` | subscribed command topic `{root}/plc01/cmd/<variable>`, ack on `cmd-resp/<variable>` |

- Values with a bad status are not published; the command topics are subscribed only while good values arrive
  (no answers for an unreachable controller, no competition with a directly publishing simulation).
- Reconfigures on BaSyx change events of a used AID; retries every 5 s while the AAS server or the OPC UA server is
  unreachable (asyncua reconnects and re-creates the subscription by itself).
- Log line every 60 s per server: telemetry messages/s, events, commands and mean call time.

## resolver

GS1 Digital Link resolver (ADR-0023), `services/resolver`, port 8096. The QR code on every part encodes its
canonical Digital Link `https://virtual-factory.example/01/04099999032808/21/<serial>` (= globalAssetId). `.example`
never resolves, so clients put the path onto this resolver (as the inspector action *Scan QR code* does).

| Request | Response |
|---|---|
| `GET /01/{gtin}/21/{serial}`, `GET /01/{gtin}` | 307 → default link (passport page); `Link` header with the linkset and all links; 404 unknown, 400 bad GTIN |
| `?linkType=gs1:pip` / `gs1:certificationInfo` / `gs1:instructions` / `gs1:sustainabilityInfo` / `vf:dpp` / `vf:aas` / `vf:aasDescriptor` | 307 → first link of that type (default link if missing) |
| `?linkType=linkset` (or `all`), `Accept: application/linkset+json` | 200 RFC 9264 linkset, relation keys are full link-type URIs (`https://gs1.org/voc/…`, `https://virtual-factory.example/voc/…`) |
| `GET /passport/01/{gtin}[/21/{serial}]` | passport page (HTML, `?lang=en\|de` or `Accept-Language`): public DPP sections only |
| `GET /.well-known/gs1resolver`, `GET /health` | resolver description, health |

Resolution: discovery (`globalAssetId` = canonical Digital Link) → registry descriptor (AAS links), and DPP API
`/v1/dppsByProductId/<DL>` (passport, certificates and instructions from the HandoverDocumentation). Links are
written with public URLs (`VF_*_PUBLIC_URL`).

```bash
SERIAL=PC3280-2026-000005      # any produced part
curl -si "http://localhost:8096/01/04099999032808/21/$SERIAL" | grep -iE '^(HTTP|location)'
curl -s -H 'Accept: application/linkset+json' "http://localhost:8096/01/04099999032808/21/$SERIAL" | jq '.linkset[0] | keys'
curl -si "http://localhost:8096/01/04099999032808/21/$SERIAL?linkType=gs1:certificationInfo" | grep -i location
open "http://localhost:8096/01/04099999032808/21/$SERIAL"          # passport page in the browser
curl -s -H 'Accept: application/linkset+json' http://localhost:8096/01/04099999032808 | jq '.linkset[0].anchor'
```

### Discovery and registry (all AAS clients)

The services resolve every AAS they do not own (ADR-0023): asset id → `/lookup/shells` → AAS id →
`/shell-descriptors` → endpoints → `/submodel-descriptors` (idShort, semanticId). The bridge finds the AIMC/AID
submodels in the submodel registry, the ops gateway finds `LineControl` from the line's asset id, and the MES finds
the AID events, LineControl, PLC01 OperationalData and the product type (thumbnail). The sustainability service
also asks the supplier environment (8191) for the batch AAS of purchased components (ADR-0028). By hand:

```bash
AAS=http://localhost:8091
b64() { python3 -c 'import sys,base64; print(base64.urlsafe_b64encode(sys.argv[1].encode()).decode().rstrip("="))' "$1"; }
link() { b64 "{\"name\":\"$1\",\"value\":\"$2\"}"; }            # assetIds query value
DL="https://virtual-factory.example/01/04099999032808/21/$SERIAL"
ID=$(curl -s "$AAS/lookup/shells?assetIds=$(link globalAssetId "$DL")" | jq -r '.result[0]')   # discovery
curl -s "$AAS/lookup/shells?assetIds=$(link serialNumber AC200-2025-0042)"                       # specific id
curl -s "$AAS/shell-descriptors/$(b64 "$ID")" | jq '{endpoints, submodels: [.submodelDescriptors[].id]}'
curl -s "$AAS/submodel-descriptors/$(b64 https://virtual-factory.example/ids/sm/LINE01/LineControl/1)" \
  | jq '{idShort, semanticId, href: .endpoints[0].protocolInformation.href}'
```

## Starting a production order

Normally the ERP releases orders (see [erp](#erp)): `curl -X POST localhost:8098/api/orders -d '{"quantity": 24}'`
queues an order that is released when LINE01 is free. Manual orders (not confirmed to the ERP): Operaton Tasklist
(`http://localhost:8092/operaton/app/tasklist/`, user demo/demo) → *Start process* → *Production order (MES)*, or
REST:

```bash
curl -X POST -H 'Content-Type: application/json' http://localhost:8092/engine-rest/process-definition/key/ProductionOrder/start -d '{"businessKey":"PO-0001","variables":{"orderId":{"value":"PO-0001","type":"String"},"quantity":{"value":24,"type":"Long"},"manualContainerExchange":{"value":true,"type":"Boolean"},"rejectRateLimit":{"value":"0.25","type":"String"}}}'
```

Commanding the line directly through the AAS (what the order process does):

```bash
curl -X POST -H 'Content-Type: application/json' "http://localhost:8091/submodels/$(printf %s 'https://virtual-factory.example/ids/sm/LINE01/LineControl/1' | base64 | tr '+/' '-_' | tr -d '=')/submodel-elements/ExecutePackMLCommand/invoke" -d '{"inputArguments":[{"value":{"modelType":"Property","idShort":"Command","valueType":"xs:string","value":"Hold"}}],"clientTimeoutDuration":"PT15S"}'
```
