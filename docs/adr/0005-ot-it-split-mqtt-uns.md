# ADR-0005: OT/IT split via MQTT UNS and edge services

- Status: accepted
- Date: 2026-10-03

## Context
The data flows must mirror a genuine manufacturing environment (NFR-07). In real plants, field devices are
controlled by a PLC, an edge layer moves data into IT systems, and an MES owns orders and genealogy.

## Decision
- Godot simulates the **OT layer only**: device models plus a virtual PLC.
- The PLC/devices publish to **MQTT 3.1.1, JSON payloads, a UNS topic tree** following the ISA-95 hierarchy
  (`vf/<site>/<area>/<line>/<device>/<class>/<datapoint>`). Godot connects via WebSocket (pure-GDScript client).
- Python **edge/IT services** do the AAS work:
  - the data bridge, configured by the machines' Asset Interfaces Description/Mapping submodels
  - the MES (workpiece AAS, quality, PCF, KPIs, orders)
  - the operation gateway (AAS Operation delegation → MQTT commands)
- Godot only **reads** AAS (AAS inspector), as any AAS consumer would.

## Consequences
+ Realistic, teachable data paths. Devices or the PLC can be replaced by real hardware.
+ Agents get two clean interfaces: AAS (standard) and MQTT.
− More moving parts (broker plus three services). Mitigated by docker compose and health checks.
