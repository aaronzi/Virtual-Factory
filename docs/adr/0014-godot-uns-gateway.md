# ADR-0014: Godot publishes the shop floor to MQTT with its own client and a generic UNS gateway

- Status: accepted
- Date: 2026-10-03

## Context

The simulation is the OT layer: devices and the virtual PLC are FMUs inside Godot. Edge and IT services need their
data and must be able to send commands, in a realistic way (MQTT + JSON, Unified Namespace; decided in planning).
Godot has no MQTT support; third-party addons exist but are unmaintained or tied to specific Godot versions, and the
project must stay exportable (WebSocket transport for a possible web build).

## Decision

- A small MQTT 3.1.1 client in GDScript (`godot/connectivity/mqtt/`): packet codec, stream parser, TCP and WebSocket
  transports, poll-driven with reconnect backoff. No addon.
- A **generic** UNS gateway (`godot/connectivity/uns/`) configured only by `godot/config/uns.json`:
  - telemetry: every FMI output of every co-simulation instance (retained; discrete values on change, continuous
    values throttled to `min_interval_s` of simulation time);
  - domain events defined declaratively (trigger variable + field variables, snapshot of the same tick), e.g.
    `part_released`, `part_inspected`, `part_sorted`, `container_full`;
  - commands for whitelisted inputs/tunable parameters with acknowledgement; "pulse" inputs (edge-triggered PackML
    command) are reset after one step;
  - session birth + online/offline status (MQTT will).
- Timestamps use the simulation time base (session wall-clock start + simulation time).
- The gateway depends only on `core` (CoSimMaster); `factory` wires it into the physics loop
  (`before_step` → probes → master step → `after_step`). `--vf-uns=<url|off>` selects or disables the broker.

## Consequences

- \+ New devices are on the UNS without gateway code; the same registry generates the AAS interface descriptions
  (ADR-0013), so topics, payloads and AAS cannot drift apart.
- \+ Events give consumers consistent multi-variable snapshots (serial + result + colour) without reassembling them
  from separate telemetry topics.
- − Outgoing QoS 1 messages are not resent after a reconnect (events lost during an outage show as `seq` gaps; open
  issue O17). About 175 messages/s in real time (O18).
