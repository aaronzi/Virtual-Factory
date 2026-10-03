# Final report - Virtual Factory (M0–M7)

## 1. What was built

A 3D training and research environment of a pneumatic-cylinder inspection and sorting line (LINE01, fictional
company VF Pneumatics GmbH) whose devices, product and workpieces have Asset Administration Shells in a local
BaSyx Go environment, connected through a realistic OT/IT data flow.

| Layer | Implementation |
|---|---|
| Shop floor (OT) | Godot 4.7 (Compatibility renderer): assembly cell (black box), belt conveyor, 2 light barriers, colour inspection QS01, UR5e robot with gripper, 2 KLT stations, stack light, safety fence; every device an FMI-3-aligned co-simulation model with a valid FMI 3.0 model description; virtual PLC (IEC 61131-3 FBs, PackML) as an FMU; Jolt physics transport |
| 3D assets | Blender 5.2 generator scripts (via Blender MCP): recognisable low-poly models with materials and decals, animations from recorded runs |
| Unified Namespace | Own MQTT 3.1.1 client in GDScript; generic UNS gateway (telemetry, declarative events, commands, session) driven by `godot/config/uns.json` (ADR-0014) |
| AAS model | 28 AAS / 211 submodels / 1134 concept descriptions from 30 IDTA and 7 custom templates; the AAS holds state and slow values, history is linked (TimeSeries LinkedSegment → InfluxDB); product passport (DPP/DBP-derived), ISA-88 recipe with IDTA ProcessParameters and BPMN procedure, Control Component Type/Instance with PackML on the interface, interfaces (AID/AIMC) generated from FMI; every value has a concept description with its unit |
| Edge / IT | AIMC-driven bridge (Lua transformations, BaSyx eventing), historian (all UNS telemetry → InfluxDB 3 Core), MES (workpiece AAS along the life cycle, quality verdict, production-based instance PCF from measured energy, KLT contents, ISO 22400 KPIs, event topics from the AID), ops gateway configured from the Control Component and AID (delegated LineControl operations incl. ExecuteSkill), Operaton BPMN engine with WorkpieceLifecycle and ProductionOrder |
| Training UI | World-space AAS inspector (live via BaSyx events, hover highlight), HMI (PackML, OEE), MES terminal with BPMN tasks, KLT, fence-door and latching E-stop interaction, data-flow visualisation, demo tour, 5 fault scenarios, DE/EN, quality presets, simulation speed, Node-RED sandbox |
| Distribution | Desktop builds for macOS (universal), Windows and Linux (x86_64); XR rig (OpenXR) behind the PlayerRig interface |

## 2. Milestones

| Milestone | Result | Commit |
|---|---|---|
| M0 Foundations | Plan, prerequisites, BaSyx Go stack, CI, architecture rules | `e57f6a6` and before |
| M1 Simulation core | FMI-3 API, co-simulation master, PLC, greybox line | `e57f6a6` |
| M2 Assets | Blender models, roofed hall, Compatibility renderer, animations | `09c879c`, `1bc1902` |
| M3 AAS model | Template engine, IDTA/custom templates, 26 AAS, provisioner | `6c0e770`, `8734328` |
| M4 OT/IT integration | UNS gateway, AIMC bridge, MES with BPMN, delegated operations | `42275bb` |
| M5 UX and training | Training UI, faults and scenarios, Node-RED sandbox | `9011251` |
| M6 Hardening | Builds, XR rig, fence door, SL01 AAS, units/concept descriptions, reports | `adfc406` |
| M7 Walkthrough feedback | Historian + TimeSeries LinkedSegment, slim AAS, production-based PCF, functional Control Component/AID, E-stop, UX fixes (hover, inspector placement, menu, captions) | this milestone |

## 3. Quality

See the [conformance report](conformance-report.md): 100 % architecture adherence, 0 complexity violations,
104 GUT and 82 Python tests, all AASX packages conformant with the IDTA test engines, draw calls within budget.

## 4. How to use it

- Start: `docker compose -f infra/docker-compose.yml up -d`, then the Godot project or a desktop build.
- Learn: [user guide](user-guide.md), [scenario walkthrough](training/scenario-walkthrough.md).
- Extend: a new device = device module + FMI model description + layout entry + asset data YAML; AAS interfaces,
  UNS topics, bridge mappings and the inspector follow automatically ([device-modules.md](architecture/device-modules.md),
  [aas-model.md §7](interfaces/aas-model.md)).

## 5. Limitations and next steps

Tracked in [open-issues.md](open-issues.md). The most relevant:
- VR is prepared but not tested on a headset (R10, O32); an XR menu panel and thumbstick scrolling are missing.
- PCF production losses are shared per session, so early parts carry noisy loss shares (R9); generated black-box
  cell data (O23).
- OPC UA as a second device protocol (AID supports it) is not implemented yet.
- Events lost during a broker outage are not resent (O17); the bridge does not store and forward (NFR-10 ◐).
- Draw-call budget has little margin with the full training UI (O31).
- Local default credentials for Operaton and no auth for Node-RED - local training use only (O34).
