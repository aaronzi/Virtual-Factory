# Edge and IT services (M4)

All services are Python packages in `services/` (one image `vf-services:dev`, repository mounted read-only at `/repo`)
and run in the compose stack `infra/docker-compose.yml`. The Godot simulation runs on the host.

```
Godot (FMUs, PLC) ──UNS/MQTT──► bridge ──REST $value──► BaSyx Go (AAS) ◄──REST── mes ◄──external tasks── Operaton
       ▲                          ▲                        │      ▲               │  ▲                    (BPMN)
       │                          └─── AIMC/AID (REST) ────┘      │ invoke        │  └──UNS events (MQTT)
       └──────UNS commands─────── ops-gateway ◄── delegation ─────┘ (LineControl) │
                                                                  ◄──────────────┘ invoke LineControl
```

| Service | Responsibility | Talks to | ADR |
|---|---|---|---|
| `provisioner` | Builds the static AAS (AASX preload) before BaSyx starts | files | 0011, 0013 |
| `bridge` | Writes UNS telemetry into the AAS as configured by AIMC/AID | MQTT, AAS | 0015 |
| `mes` | Sessions, workpiece instance AAS, quality verdict, PCF, KLT contents, energy/CO₂e, power time series, KPIs; external-task worker of both BPMN processes; UNS event → BPMN message correlation | MQTT, AAS, Operaton | 0016 |
| `ops-gateway` | Executes the delegated LineControl operations as UNS commands | AAS (delegation), MQTT | 0017 |
| `bpmn` | Operaton 2.1.5: process engine, Cockpit, Tasklist | – | 0016 |
| `nodered` (profile `sandbox`, optional) | Learner sandbox with example flows (UNS explorer, reject alarm, read the AAS, call an AAS operation); port 1880, no auth, outside the core data path; publishes only `{root}/sandbox/alert` | MQTT, AAS | – |

## Configuration (environment variables)

| Variable | Default | Used by |
|---|---|---|
| `VF_AAS_URL` | `http://localhost:8091` | bridge, mes |
| `VF_MQTT_URL` | `mqtt://localhost:1883` | bridge, mes, ops-gateway |
| `VF_BPMN_URL` | `http://localhost:8092/engine-rest` | mes |
| `VF_AAS_PUBLIC_URL` | `http://localhost:8091` | mes (thumbnail links of workpiece AAS) |
| `VF_RETENTION` | `500` | mes: rolling window of workpiece AAS kept per session |
| `VF_AAS_EVENTS_TOPIC` | `vf/basyx/submodelrepository/#` | bridge: BaSyx CloudEvents (empty = off) |
| `VF_BRIDGE_MIN_INTERVAL` | `1.0` | bridge: minimum seconds between writes of a numeric element |
| `VF_CONTROLLER` / `VF_OPS_PORT` | `PLC01` / `8095` | ops-gateway |
| `VF_REPO` | repository root | all (asset data, templates, `uns.json`, `bpmn/`) |

## bridge

- Loads every AIMC 2.0 submodel (`semanticId` filter) with `extent=withBlobValue`, resolves sources into the AID
  (topic = `forms.href`, JSON key = `properties.Value.key`) and sinks (submodel + idShort path, value type).
- Transformations: Lua `aimc_main(sources)` in a sandbox (state codes → `OperatingState`).
- Write policy: discrete values on change; numbers ≤ 1 per second and element, 0.2 % deadband; value-only PATCH.
- Reloads on BaSyx events for AIMC/AID submodels and every 5 minutes.

## mes

**Workpiece instance AAS** (`aas/data/blueprints/workpiece_instance.yaml`, built with the provisioner's
`BuildContext` together with the product type, strictly validated before upload):

| Stage (BPMN task) | Trigger | Content |
|---|---|---|
| released (`workpiece-create`) | `part_released` | Nameplate, DppMetadata, ExecutedProcesses OP10–OP70 (cell test data), AssetLocation (CV01) |
| inspected (`workpiece-record-inspection`) | `part_inspected` | + OP75/OP80, QualityInspection (verdict vs. recipe limits), MeasurementValue ×2 |
| packed (`workpiece-record-packing`) | `part_sorted` | + OP90, run completed, CarbonFootprint (actual PCF), AssetLocation (KLT, slot), KLT contents |
| lost (`workpiece-mark-lost`) | 5 min timeout | run aborted |

- Values the simulation does not produce (torques, forces, lots of the black-box assembly cell) are derived
  deterministically per serial around the recipe values; lots change every 250 parts (`cell_data.py`).
- Verdict: leak rate and stroke time (cell) and ΔE*ab (QS01) against the formula limits of the master recipe; the
  PLC sorts by colour only, so a part with a failed cell test packed into KLT A raises the "mis-sorted" user task.
- PCF = Σ BulkCount × component PCF (BoM of the product type, component AAS found by `globalAssetId`) + line energy
  per part (rolling 5 min) × emission factor of LINE01.
- KLT contents: `HierarchicalStructures` of KLTA01/KLTB01, station → `Box` → one Node + HasPart per part; cleared on
  `container_exchanged`.
- Every 10 s: `OperationalCO2eq`/`LastUpdate` per device, line totals in LINE01/EnergyConsumption, a power record in
  each `PowerTimeSeries` (ring buffer, 180 records = 30 min). Every 15 s: ISO 22400 KPI elements of LINE01 from the
  PackML state durations and counters.
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

## ops-gateway

`POST /operations/{ExecutePackMLCommand|ExchangeContainer|SetAutoExchange}` with the OperationVariable array sent by
BaSyx; returns the output variables (`Accepted`, `State`, `Message`). `GET /health`. PackML commands are checked
against the state model before they are sent and confirmed by the resulting state. Timeouts: 3 s acknowledgement,
10 s state.

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
