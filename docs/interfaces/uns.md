# Unified Namespace (UNS) – MQTT interface of the shop floor

The registry [`godot/config/uns.json`](../../godot/config/uns.json) is the single source for the Godot UNS
gateway (`godot/connectivity/uns/`) and the AAS Asset Interfaces Description (provisioner, ADR-0005/0013). The
edge services read the topics from the AAS at runtime (bridge: AIMC/AID properties; ops gateway: Control Component
→ AID actions; MES: AID events - ADR-0015/0020); only the MES still uses the registry directly for the session
birth and its KPI topics. This page describes how the Godot gateway implements it.

**OPC UA path (ADR-0024).** Controllers listed in `opcua.servers` (today PLC01) are not published by the Godot
gateway: the simulated PLC CPU feeds its communication module `plc-comm` over the backplane, `plc-comm` serves an
OPC UA server, and the **edge connector** publishes PLC01's telemetry, events and acknowledgements with exactly the
topics and payloads below (see [OPC UA path](#opc-ua-path-plc01)). For consumers nothing changes.

- Broker: Mosquitto, MQTT 3.1.1, `mqtt://localhost:1883` (TCP) and `ws://localhost:9001` (WebSocket, subprotocol
  `mqtt`). Godot uses its own GDScript client (`godot/connectivity/mqtt/`, no addon).
- Topic root (ISA-95 enterprise/site/area/line): `vf/plant01/final-assembly/line01` = `{root}`.
- `{device}` = FMI instance name in lower case (`plc01`, `klta01`); `{variable}` = FMI variable name.
- Payloads are compact JSON objects; value key `v`, timestamp key `ts`.

## Timestamps

`ts` is ISO 8601 UTC with milliseconds on the **simulation time base**: wall clock at session start +
simulation time (`CoSimMaster.time`). Faster-than-real-time headless runs therefore produce ordered,
consistent timestamps that may lie in the future. All messages of one physics tick share the same `ts`.

## Session

| Topic | Payload | QoS / retain |
|---|---|---|
| `{root}/session` | `{"id": "S-20261003T131500Z-3fa2", "started": ts, "layout": "line1.layout.json", "devices": ["AC01", …, "PLC01"], "ts": ts}` | 1 / retained |
| `{root}/status` | `{"v": "online", "ts": ts}` on connect, `{"v": "offline", "ts": ts}` on shutdown | 1 / retained |

- The session id is created once per factory run; the birth message is republished (same id) after every
  reconnect, followed by the full telemetry state.
- MQTT will: `{"v": "offline"}` on `{root}/status` (retained), published by the broker if Godot disappears.

## Telemetry

`{root}/{device}/{variable}` – every FMI variable with causality `output` of every instance, payload
`{"v": value, "ts": ts}`, QoS 0, retained. PLC01: published by the edge from the OPC UA monitored items, `ts` =
the OPC UA SourceTimestamp (same simulation time base).

- Published on change only. Discrete values (Boolean/Int32/String, or variability `discrete`) immediately;
  continuous Float64 values at most every `telemetry.min_interval_s` (0.1 s simulation time; the latest value is
  sent once the interval has elapsed).
- The full current state is published once after each (re)connect.
- Non-finite floats are sent as `null`.
- Rate: about 170–210 messages/s at real time (dominated by continuous values such as `energy`,
  `operating_hours`, robot joints at 10 Hz); about 5 000 messages/s in the headless 60-fps line run (~27× real time).

## Events

`{root}/{device}/event/{event}` – QoS 1, not retained. Flat JSON object:

```json
{"event": "part_sorted", "device": "PLC01", "session": "S-20261003T133337Z-a834", "seq": 30,
 "ts": "2026-10-03T13:36:54.052Z", "serial": "PC3280-2026-000009", "container": 2, "slot": 1}
```

- An event fires after a master step when its `trigger` variable changed since the previous step (and equals
  `when`, if given). Fields are read in the same tick as the trigger change. No events for the initial state.
- `seq` counts events per session and publisher, also while disconnected (events are not buffered), so consumers can
  detect gaps. PLC01's events (`part_inspected`, `part_sorted`) come from the edge (OPC UA events of the PLC) and
  carry the PLC's own counter; the other devices share the counter of the Godot gateway.
- Definitions: `part_released` (AC01), `part_inspected` / `part_sorted` (PLC01), `container_full` /
  `container_exchanged` (KLTA01, KLTB01). One serial goes released → inspected → sorted.
- `part_sorted` comes from the PLC outputs `sorted_count/serial/target/slot` (set in the same PLC scan when the robot
  reports job done). A KLT exchange is only requested when no robot job to that KLT is in progress, so
  `container_exchanged` always follows the last `part_sorted` of the old container.

## Commands

`{root}/{device}/cmd/{variable}` for each variable in `commands.writable` (QoS 1), payload
`{"v": value, "corr": "optional id", "source": "optional name"}`.

| Variable | Type | Meaning |
|---|---|---|
| `PLC01.packml_command` | Int32, pulse | 1 Reset, 2 Start, 3 Stop, 4 Hold, 5 Unhold, 6 Suspend, 7 Unsuspend, 8 Abort, 9 Clear |
| `PLC01.klt_exchange_command` | Int32, pulse | 1 = exchange KLT A, 2 = KLT B (only if it holds parts; waits for a running robot job) |
| `PLC01.auto_exchange` | Boolean, tunable parameter | automatic exchange of full KLTs after `exchange_delay` |
| `PLC01.unit_mode_command` | Int32, pulse | PackML unit mode 1 Production, 2 Maintenance, 3 Manual (accepted in STOPPED, IDLE, ABORTED; output `unit_mode`) |
| `CV01.motor_fault` | Boolean, input | fault injection: conveyor drive trip |
| `QS01.contamination`, `QS01.drift` | Float64, tunable parameters | fault injection: dirty colour sensor lens (0..1), calibration offset |
| `LB01.misalignment`, `LB02.misalignment` | Float64, input | fault injection: 0 aligned … 1 beam lost (signal stuck) |
| `AC01.defect_rate_missing_cap`, `AC01.defect_rate_wrong_cap` | Float64, tunable parameters | defect probabilities per part |
| `RB01.protective_stop` | Boolean, input | robot protective stop (fence door) |
| `RB01.finger_wear_rate` | Float64, tunable parameter | wear of the gripper finger pads per grip in m (design 4e-10; scenario `gripper_wear` 4.5e-5) |
| `RB01.gripper_maintenance_reset` | Boolean, pulse | finger change of GR01 done (rising edge): `finger_wear`, `grip_cycles`, `grasp_retries` restart at 0; sent by the ops gateway (skill `Maintain`, ADR-0029) |

Fault variables and the resulting PLC alarms (`PLC01.alarm_code/alarm_text`): [scenarios.md](scenarios.md).

- Validation on receipt: JSON object with `v`; numbers/booleans converted to the FMI type (integers must be integral
  and in range; booleans accept `true/false/0/1`). Invalid commands are rejected immediately.
- Valid commands are applied between master steps (from the physics loop). Pulse variables (`commands.pulse`) hold
  the value for exactly one master step, are reset to 0 and stay 0 for one more step, so repeated identical commands
  still produce an edge; further pulses for the same variable are queued.
- Ack on `{root}/{device}/cmd-resp/{variable}` (QoS 1, not retained):
  `{"corr": "t1", "accepted": true, "reason": "", "v": 4, "ts": ts}`. `reason` explains a rejection (empty when
  accepted); `v` is the applied value (`null` when rejected).
- PLC01 commands are taken by the edge (only while the OPC UA server delivers valid data) and executed as OPC UA
  method calls `Commands/<variable>(Value)`; the ack carries the call result (`reason` = OPC UA status, e.g.
  `BadNotConnected: …`) and a wall-clock `ts`.

## Maintenance results (ADR-0029)

Section `maintenance` of the registry: the maintenance service publishes its condition monitoring results like
telemetry (`{"v": value, "ts": time of the latest measurement}`, QoS 1, retained); the historian records them in
table `maintenance` (tags `session`, `component`).

| Topic | Payload `v` |
|---|---|
| `{root}/maintenance/{component}/health_index` | Float64 0..1 (1 - wear / limit) |
| `{root}/maintenance/{component}/wear` | Float64, indicator value (GR01: finger wear in m) |
| `{root}/maintenance/{component}/rul_cycles`, `rul_cycles_low` | Float64, remaining cycles (median, 90 % lower bound) |
| `{root}/maintenance/{component}/rul_hours`, `rul_hours_low` | Float64 h at the current throughput (`null` without production) |
| `{root}/maintenance/{component}/confidence`, `throughput` | Float64 0..1 / cycles per hour |
| `{root}/maintenance/{component}/health_state`, `order` | String Good / Warning / Alarm / Unknown; open maintenance order (empty = none) |
| `{root}/maintenance/active_alarms` | String: advisory alarm word (e.g. `901`), read by the alarms service like `plc01/active_alarms` |

`{component}` = component tag in lower case (`gr01`).

## OPC UA path (PLC01)

```text
Godot PLC01 (FMU, CPU) --backplane tcp:4841--> plc-comm (OPC UA server :4840) --opc.tcp--> edge --> broker
                                                        ^-- ops gateway (method calls, monitored items)
```

- Registry: `opcua.enabled`, `opcua.servers.PLC01` = `endpoint` (opc.tcp://localhost:4840/vf/plc01), `namespace`
  (urn:virtual-factory:plant01:line01:plc01), `backplane` (tcp://localhost:4841), `publishing_interval_ms`,
  `packml_tags` / `packml_commands` (FMI variable → PackML node, see below).
- Address space (namespace index 2, string NodeIds `PLC01.<path>`, built by `vf_common.opcua_plc`):

  | Node | Content |
  |---|---|
  | `PLC01` | PackML base object (structure after OPC 30050): `TagID`, `PackMLVersion` |
  | `PLC01.Status.*` | `StateCurrent` (packml_state), `UnitModeCurrent` (unit_mode), `MachSpeed` (belt_speed), `CurMachSpeed` (cv_speed_setpoint) |
  | `PLC01.Admin.*` | `ProdProcessedCount` (parts_total), `ProdGoodCount` (parts_ok), `ProdDefectiveCount` (parts_nok), `AlarmCode`, `AlarmText`, `AlarmCount` |
  | `PLC01.BaseStateMachine` | `CurrentState` (state name), methods `Reset` `Start` `Stop` `Hold` `Unhold` `Suspend` `Unsuspend` `Abort` `Clear` |
  | `PLC01.SetUnitMode(UnitMode)` | writes `unit_mode_command` |
  | `PLC01.Program.Inputs/Outputs/Parameters.<variable>` | all other FMI variables (I/O image of the controlled devices, tag table) |
  | `PLC01.Commands.<variable>(Value)` | one method per writable variable (`packml_command`, `klt_exchange_command`, `auto_exchange`, `unit_mode_command`) |
  | `PLC01.Diagnostics.*` | `CpuConnected`, `SessionId`, `ImageUpdates` |
  | `PartInspectedEventType`, `PartSortedEventType` | event types below BaseEventType, fields `Session`, `Seq` + event fields; emitted by `PLC01` |

- Values carry the CPU's timestamp as SourceTimestamp. Without a CPU on the backplane they have the status
  `BadNoCommunication`; methods answer `BadNotConnected`. Method results: Good, `BadTimeout`, `BadTypeMismatch`,
  `BadNotExecutable` (rejected by the CPU).
- **Backplane** (Godot `PlcBackplane` ↔ `plc-comm`): newline-delimited JSON over TCP, the CPU connects.
  CPU → module: `hello {protocol 1, device, model, session}`; after the module's `welcome {endpoint, namespace}`
  (only then the link counts as up): `image {ts, values}` (changed values, all values first), `event {event, ts,
  payload}` (the UNS event payload), `result {id, accepted, reason, v}`. Module → CPU: `write {id, variable, v}`
  (applied between two master steps like a UNS command, incl. pulse handling). The session id travels with
  hello/events (a simulation concept). Reconnect 1 … 10 s, one warning per outage.
- Edge: subscribes all AID OPC UA properties (sampling 0, queue 50, publishing interval 100 ms) and the event
  types, publishes them on the MQTT affordance of the same name; commands only while values are good.

## Godot runtime options

- Default on, broker `broker.websocket` from the registry. `--vf-uns=ws://host:port` or `--vf-uns=mqtt://host:port`
  overrides the broker, `--vf-uns=off` disables the gateway.
- `tools/run_line_simulation.sh` passes `--vf-uns=off` unless `VF_UNS` is set (`VF_UNS=ws://localhost:9001`).
- OPC UA path: on together with the gateway (backplane `opcua.servers.<device>.backplane`, reconnect 1 … 10 s).
  `--vf-backplane=off` publishes PLC01 directly over MQTT again (the AAS Control Component still points to OPC UA,
  so LineControl operations then report `BadNotConnected`); `--vf-backplane=tcp://host:port` overrides the
  address and links even with `--vf-uns=off`.
- Broker unreachable: the factory keeps running; the client reconnects with exponential backoff (1 s … 30 s) and logs
  one warning per outage.
- Client limits: QoS 0/1 only; outgoing QoS 1 messages are not resent after a reconnect (retained telemetry is
  republished; events sent during an outage are lost, visible as `seq` gaps).

## Secure profile (ADR-0027)

With `infra/docker-compose.secure.yml` the broker has no anonymous access: every client has its own account and
a topic ACL (`infra/mosquitto/secure/acl`, generated from `infra/security.yaml`). The Godot gateway (`godot`)
publishes telemetry, events, acks and the session and subscribes to commands; the edge (`edge`) publishes only
PLC01; **only `ops-gateway` may publish `{root}/+/cmd/+`**; `maintenance` publishes `{root}/maintenance/#`;
consumers (historian, alarms, MES, bridge, sustainability) only read; `explorer` is a read-only account for MQTT
Explorer. Godot takes its account from `--vf-secure` / `--vf-uns-user=` / `--vf-uns-password=`.

## Consumers

| Consumer | Uses |
|---|---|
| AAS (provisioner) | AID properties/actions/events generated from this registry and the FMI model descriptions (ADR-0013) |
| bridge | telemetry topics as configured by the AIMC in the AAS - state and slow values only (ADR-0015, ADR-0019) |
| historian | all telemetry `{root}/+/+` (every FMI output of every device) + session birth → InfluxDB 3 (ADR-0019) |
| sustainability | session birth (MeasurementStart, KPI and loss-allocation reset; ADR-0025) |
| alarms | PLC01 `active_alarms` (alarm word; `alarm_code` as fallback) and `packml_state`, session/status, all events `{root}/+/event/+`, commands `{root}/+/cmd/+` and acks `{root}/+/cmd-resp/+` → ISA-18.2 alarm states and the event journal in TimescaleDB (ADR-0026) |
| mes | events (→ BPMN messages; topics discovered from the AID event affordances in the AAS, ADR-0020), session birth and PLC01 `packml_state`/counters (KPIs) from this registry |
| ops-gateway | PLC01 over OPC UA (method calls, monitored items `packml_state`, `unit_mode`) resolved from LINE01 LineControl → PLC01 Control Component endpoints → AID `InterfaceOPCUA` (ADR-0024); MQTT commands + acks for MQTT affordances (`forms`, `ackForms`, ADR-0017, ADR-0020) |
| edge | OPC UA → UNS for PLC01 (telemetry, events, acks of PLC01 commands), configured from the AID (OPC UA + MQTT interface, ADR-0024) |
| BaSyx Go | publishes its own CloudEvents under `vf/basyx/...` (not part of this registry) |
| Godot training UI | `vf/basyx/#` (inspector live values, data-flow view) |
| Node-RED sandbox | events; publishes `{root}/sandbox/alert` (outside the registry, consumed by nobody) |

See [services.md](services.md).
