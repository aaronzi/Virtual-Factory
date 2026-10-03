# Edge and IT services (M4)

All services are Python packages in `services/` (one image `vf-services:dev`, repository mounted read-only at `/repo`)
and run in the compose stack `infra/docker-compose.yml`. The Godot simulation runs on the host.

```
Godot (FMUs, PLC) ──UNS/MQTT──► bridge ──REST $value──► BaSyx Go (AAS) ◄──REST── mes ◄──external tasks── Operaton
       ▲                          ▲                        │      ▲               │  ▲                    (BPMN)
       │                          └─── AIMC/AID (REST) ────┘      │ invoke        │  └──UNS events (MQTT)
       └──────UNS commands─────── ops-gateway ◄── delegation ─────┘ (LineControl) │
       │                                                          ◄──────────────┘ invoke LineControl
       └──UNS telemetry (MQTT)──► historian ──line protocol──► InfluxDB 3 ◄──SQL── mes (PCF), clients via the
                                                                                 AAS TimeSeries LinkedSegment
```

| Service | Responsibility | Talks to | ADR |
|---|---|---|---|
| `provisioner` | Builds the static AAS (AASX preload) before BaSyx starts | files | 0011, 0013 |
| `bridge` | Writes UNS telemetry into the AAS as configured by AIMC/AID (state and slow values only) | MQTT, AAS | 0015, 0019 |
| `historian` | Records the UNS telemetry of all devices (every FMI output) in InfluxDB 3 | MQTT, InfluxDB | 0019 |
| `influxdb3` | InfluxDB 3 Core 3.12.0: time-series database of the historian, port 8181, no auth, tmpfs | – | 0019 |
| `mes` | Sessions, workpiece instance AAS, quality verdict, production-based PCF (energy from the historian), KLT contents, energy/CO₂e, KPIs; external-task worker of both BPMN processes; UNS event → BPMN message correlation (event topics from the AID) | MQTT, AAS, Operaton, InfluxDB | 0016, 0019, 0020 |
| `ops-gateway` | Executes the delegated LineControl operations (incl. Control Component skills) as UNS commands; endpoints resolved from Control Component → AID | AAS (delegation, configuration), MQTT | 0017, 0020 |
| `bpmn` | Operaton 2.1.5: process engine, Cockpit, Tasklist | – | 0016 |
| `nodered` (profile `sandbox`, optional) | Learner sandbox with example flows (UNS explorer, reject alarm, read the AAS, call an AAS operation); port 1880, no auth, outside the core data path; publishes only `{root}/sandbox/alert` | MQTT, AAS | – |

## Configuration (environment variables)

| Variable | Default | Used by |
|---|---|---|
| `VF_AAS_URL` | `http://localhost:8091` | bridge, mes, ops-gateway |
| `VF_MQTT_URL` | `mqtt://localhost:1883` | bridge, mes, ops-gateway |
| `VF_BPMN_URL` | `http://localhost:8092/engine-rest` | mes |
| `VF_AAS_PUBLIC_URL` | `http://localhost:8091` | mes (thumbnail links of workpiece AAS) |
| `VF_RETENTION` | `500` | mes: rolling window of workpiece AAS kept per session |
| `VF_AAS_EVENTS_TOPIC` | `vf/basyx/submodelrepository/#` | bridge, mes, ops-gateway: BaSyx CloudEvents for reloads (empty = off) |
| `VF_BRIDGE_MIN_INTERVAL` | `5.0` | bridge: minimum seconds between writes of a numeric element |
| `VF_INFLUX_URL` | `http://localhost:8181` | historian, mes (compose: `http://influxdb3:8181`); database and batching in `infra/historian.json` |
| `VF_LINE` / `VF_OPS_PORT` | `LINE01` / `8095` | ops-gateway: line whose `LineControl` submodel is the entry of the resolution; HTTP port |
| `VF_REPO` | repository root | all (asset data, templates, `uns.json`, `bpmn/`) |

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
- Writes each sample with its UNS `ts` (simulation time base, ms precision) into database `vf`: one table per
  device (lower-case instance name = UNS segment, e.g. `cv01`), one field per FMI output (Float64 → float,
  Int32 → integer, Boolean → boolean, String → string), tag `session`. Samples of one tick share one row.
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

## mes

**Workpiece instance AAS** (`aas/data/blueprints/workpiece_instance.yaml`, built with the provisioner's
`BuildContext` together with the product type, strictly validated before upload):

| Stage (BPMN task) | Trigger | Content |
|---|---|---|
| released (`workpiece-create`) | `part_released` | Nameplate, DppMetadata, ExecutedProcesses OP10–OP70 (cell test data), AssetLocation (CV01) |
| inspected (`workpiece-record-inspection`) | `part_inspected` | + OP75/OP80, QualityInspection (verdict vs. recipe limits), MeasurementValue ×2 |
| packed (`workpiece-record-packing`) | `part_sorted` | + OP90, run completed, CarbonFootprint (production-based PCF: A1-A3 total, A1 components, A3 manufacturing), AssetLocation (KLT, slot), KLT contents |
| lost (`workpiece-mark-lost`) | 5 min timeout | run aborted |

- Values the simulation does not produce (torques, forces, lots of the black-box assembly cell) are derived
  deterministically per serial around the recipe values; lots change every 250 parts (`cell_data.py`).
- Verdict: leak rate and stroke time (cell) and ΔE*ab (QS01) against the formula limits of the master recipe; the
  PLC sorts by colour only, so a part with a failed cell test packed into KLT A raises the "mis-sorted" user task.
- PCF: production-based, per part from the historian (method in [aas-model.md §6a](aas-model.md#6a-runtime-submodels-m4)):
  components (A1) + energy of the part's assembly-cell cycle and its residence-time share of the downstream devices
  + compressed air, × emission factor of LINE01, + allocated production losses (A3); written as three
  CarbonFootprint entries. Fallback without historian: line energy per part (rolling 5 min) from the AAS counters.
- KLT contents: `HierarchicalStructures` of KLTA01/KLTB01, station → `Box` → one Node + HasPart per part; cleared on
  `container_exchanged`.
- Every 10 s: `OperationalCO2eq`/`LastUpdate` per device, line totals in LINE01/EnergyConsumption. Every 15 s:
  ISO 22400 KPI elements of LINE01 from the PackML state durations and counters. The history of power and all other
  outputs is in the historian (TimeSeries LinkedSegment), not written by the MES.
- A new session birth (Godot start) or an MES start removes the workpiece AAS and processes of the previous session.

**External-task topics**

| Topic | Process | Effect |
|---|---|---|
| `workpiece-create`, `workpiece-record-inspection`, `workpiece-record-packing`, `workpiece-mark-lost` | WorkpieceLifecycle | see table above; sets `verdict`, `plannedContainer`, `correctContainer`, `pcf` |
| `line-start` | ProductionOrder | SetAutoExchange(!manual), Clear/Reset/Start as needed, counter baseline |
| `order-progress` | ProductionOrder | reads `parts_ok`/`parts_nok` from PLC01/OperationalData; `orderDone`, `rejectAlarm` (≥ 10 parts in window and rate > limit) |
| `line-command` | ProductionOrder | ExecutePackMLCommand(`packmlCommand` input parameter) |
| `line-exchange-container` | ProductionOrder | ExchangeContainer(`container`) |
| `order-close` | ProductionOrder | SetAutoExchange(true), summary |

**Messages**: `PartReleased` (starts WorkpieceLifecycle, business key = serial), `PartInspected`, `PartSorted`
(correlated by serial, retried for 60 s), `ContainerFull` (all waiting ProductionOrder instances).

**Event discovery (ADR-0020)**: the MES subscribes to the topics of all AID event affordances on the AAS server
(`InteractionMetadata.events.<name>.forms.href` of every AssetInterfacesDescription) and maps the affordance name
(`part_released`, `part_inspected`, `part_sorted`, `container_full`, `container_exchanged`) to the messages above;
messages on topics the AAS does not describe are ignored. Reloaded (debounced 2 s) on BaSyx change events of AID
submodels and every 5 min; if discovery fails or finds no events, the previous topics are kept and an error is
logged (no fallback to `uns.json`). Still taken from the UNS registry: the session birth `{root}/session` (a
namespace topic of the Godot gateway, not an asset affordance) and the PLC01 KPI telemetry topics.

## ops-gateway

`POST /operations/{ExecutePackMLCommand|ExchangeContainer|SetAutoExchange|ExecuteSkill}` with the OperationVariable
array sent by BaSyx; returns the output variables (`Accepted`, `State` for ExecutePackMLCommand/ExecuteSkill,
`Message`). PackML commands are checked against the state model before they are sent and confirmed by the resulting
state. Timeouts: 3 s acknowledgement, 10 s state.

**Configuration from the AAS (ADR-0020).** Nothing about topics is configured in the gateway or read from
`uns.json`:

```
LINE01/LineControl.ControlComponent ──► PLC01/ControlComponentInstance
    Endpoints.PackMLState     ──EndpointReference──► AID properties.packml_state  (topic, value key v)
    Endpoints.PackMLCommand   ──EndpointReference──► AID actions.packml_command    ┐ forms: topic, QoS, retain, op
    Endpoints.ContainerExchange ─────────────────► AID actions.klt_exchange_command ├ input: keys v / corr / source
    Endpoints.AutoExchange    ───────────────────► AID actions.auto_exchange       ┘ ackForms + output: ack topic, keys
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

- Checks before anything is sent: skill exists and is not `Disabled`; `Mode` is one of the skill's `Modes` (empty
  = first mode; the mode is validated only, the PLC has no unit-mode endpoint); parameter names, Direction In,
  type, Min/Max and enumerated values from the skill description.
- `ExchangeContainer(Container)` is a shortcut for the skill `ExchangeContainer` (same validation).

```bash
curl -X POST -H 'Content-Type: application/json' "http://localhost:8091/submodels/$(printf %s 'https://virtual-factory.example/ids/sm/LINE01/LineControl/1' | base64 | tr '+/' '-_' | tr -d '=')/submodel-elements/ExecuteSkill/invoke" -d '{"inputArguments":[{"value":{"modelType":"Property","idShort":"Skill","valueType":"xs:string","value":"Produce"}},{"value":{"modelType":"Property","idShort":"Mode","valueType":"xs:string","value":"Production"}},{"value":{"modelType":"Property","idShort":"Parameters","valueType":"xs:string","value":"{\"auto_exchange\": true}"}}],"clientTimeoutDuration":"PT30S"}'
```

## Starting a production order

Operaton Tasklist (`http://localhost:8092/operaton/app/tasklist/`, user demo/demo) → *Start process* →
*Production order (MES)*, or REST:

```bash
curl -X POST -H 'Content-Type: application/json' http://localhost:8092/engine-rest/process-definition/key/ProductionOrder/start -d '{"businessKey":"PO-0001","variables":{"orderId":{"value":"PO-0001","type":"String"},"quantity":{"value":24,"type":"Long"},"manualContainerExchange":{"value":true,"type":"Boolean"},"rejectRateLimit":{"value":"0.25","type":"String"}}}'
```

Commanding the line directly through the AAS (what the order process does):

```bash
curl -X POST -H 'Content-Type: application/json' "http://localhost:8091/submodels/$(printf %s 'https://virtual-factory.example/ids/sm/LINE01/LineControl/1' | base64 | tr '+/' '-_' | tr -d '=')/submodel-elements/ExecutePackMLCommand/invoke" -d '{"inputArguments":[{"value":{"modelType":"Property","idShort":"Command","valueType":"xs:string","value":"Hold"}}],"clientTimeoutDuration":"PT15S"}'
```
