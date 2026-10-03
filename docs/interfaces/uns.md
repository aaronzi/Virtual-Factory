# Unified Namespace (UNS) – MQTT interface of the shop floor

The registry [`godot/config/uns.json`](../../godot/config/uns.json) is the single source for the Godot UNS
gateway (`godot/connectivity/uns/`) and the AAS Asset Interfaces Description (provisioner, ADR-0005/0013). The
edge services read the topics from the AAS at runtime (bridge: AIMC/AID properties; ops gateway: Control Component
→ AID actions; MES: AID events - ADR-0015/0020); only the MES still uses the registry directly for the session
birth and its KPI topics. This page describes how the Godot gateway implements it.

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
`{"v": value, "ts": ts}`, QoS 0, retained.

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
- `seq` counts events per session, also while disconnected (events are not buffered), so consumers can detect gaps.
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
| `CV01.motor_fault` | Boolean, input | fault injection: conveyor drive trip |
| `QS01.contamination`, `QS01.drift` | Float64, tunable parameters | fault injection: dirty colour sensor lens (0..1), calibration offset |
| `LB01.misalignment`, `LB02.misalignment` | Float64, input | fault injection: 0 aligned … 1 beam lost (signal stuck) |
| `AC01.defect_rate_missing_cap`, `AC01.defect_rate_wrong_cap` | Float64, tunable parameters | defect probabilities per part |
| `RB01.protective_stop` | Boolean, input | robot protective stop (fence door) |

Fault variables and the resulting PLC alarms (`PLC01.alarm_code/alarm_text`): [scenarios.md](scenarios.md).

- Validation on receipt: JSON object with `v`; numbers/booleans converted to the FMI type (integers must be integral
  and in range; booleans accept `true/false/0/1`). Invalid commands are rejected immediately.
- Valid commands are applied between master steps (from the physics loop). Pulse variables (`commands.pulse`) hold
  the value for exactly one master step, are reset to 0 and stay 0 for one more step, so repeated identical commands
  still produce an edge; further pulses for the same variable are queued.
- Ack on `{root}/{device}/cmd-resp/{variable}` (QoS 1, not retained):
  `{"corr": "t1", "accepted": true, "reason": "", "v": 4, "ts": ts}`. `reason` explains a rejection (empty when
  accepted); `v` is the applied value (`null` when rejected).

## Godot runtime options

- Default on, broker `broker.websocket` from the registry. `--vf-uns=ws://host:port` or `--vf-uns=mqtt://host:port`
  overrides the broker, `--vf-uns=off` disables the gateway.
- `tools/run_line_simulation.sh` passes `--vf-uns=off` unless `VF_UNS` is set (`VF_UNS=ws://localhost:9001`).
- Broker unreachable: the factory keeps running; the client reconnects with exponential backoff (1 s … 30 s) and logs
  one warning per outage.
- Client limits: QoS 0/1 only; outgoing QoS 1 messages are not resent after a reconnect (retained telemetry is
  republished; events sent during an outage are lost, visible as `seq` gaps).

## Consumers

| Consumer | Uses |
|---|---|
| AAS (provisioner) | AID properties/actions/events generated from this registry and the FMI model descriptions (ADR-0013) |
| bridge | telemetry topics as configured by the AIMC in the AAS - state and slow values only (ADR-0015, ADR-0019) |
| historian | all telemetry `{root}/+/+` (every FMI output of every device) + session birth → InfluxDB 3 (ADR-0019) |
| mes | events (→ BPMN messages; topics discovered from the AID event affordances in the AAS, ADR-0020), session birth and PLC01 `packml_state`/counters (KPIs) from this registry |
| ops-gateway | commands + acks, PLC01 `packml_state`; topics, QoS and keys resolved from LINE01 LineControl → PLC01 Control Component endpoints → AID actions (`forms`, `ackForms`) / property, not from this registry (ADR-0017, ADR-0020) |
| BaSyx Go | publishes its own CloudEvents under `vf/basyx/...` (not part of this registry) |
| Godot training UI | `vf/basyx/#` (inspector live values, data-flow view) |
| Node-RED sandbox | events; publishes `{root}/sandbox/alert` (outside the registry, consumed by nobody) |

See [services.md](services.md).
