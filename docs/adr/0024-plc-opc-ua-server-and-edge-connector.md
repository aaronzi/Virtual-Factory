# ADR-0024: PLC01 on OPC UA – communication module, backplane link and edge connector

- Status: accepted
- Date: 2026-10-03
- Refines: [ADR-0005](0005-ot-it-split-mqtt-uns.md), [ADR-0014](0014-godot-uns-gateway.md),
  [ADR-0020](0020-control-component-and-aid-drive-commands.md); extends [ADR-0013](0013-aas-interfaces-generated-from-fmi.md)

## Context
Until now the simulation published every device, including the line PLC, directly to MQTT (Godot UNS gateway),
and the AID of every asset described only that MQTT interface. A real line controller does not speak UNS: it exposes
an OPC UA server (increasingly with the PackML companion specification OPC 30050), and an edge gateway subscribes to
it and publishes to the broker. Commands from the IT side reach the PLC as OPC UA method calls, not as MQTT messages.
The self-review asked for this realism without losing the generated, AAS-driven configuration (ADR-0013, ADR-0020).

Godot has no OPC UA stack, and none is maintained for GDScript; a C++ GDExtension (open62541) would break the
pure-GDScript, export-everywhere setup and the CI on plain Godot binaries.

## Decision
**Split the PLC like real hardware: CPU in Godot, communication module as a separate process.**
- The PLC program stays an FMU in Godot (ADR-0008). A new GDScript class `PlcBackplane`
  (`godot/connectivity/plc_link/`) links the CPU to the **communication module** `plc-comm` (new service,
  `services/plc_comm`, Python asyncua 2.0.1) over a "backplane": newline-delimited JSON over TCP, port 4841, the CPU
  connects. Each physics tick it sends the changed process image (all FMI inputs, outputs, parameters, with the
  simulation-time timestamp), the UNS events of the controller and the results of writes; the module sends writes,
  which Godot applies between two master steps with the same validation and pulse logic as UNS commands
  (`UnsCommands`). Godot still runs standalone: without `plc-comm` the link retries in the background.
- `plc-comm` serves **opc.tcp://…:4840/vf/plc01** (security None/Anonymous, see below). The address space is
  engineered at start-up from the FMI model description and the UNS registry (`vf_common.opcua_plc`), like a PLC
  project downloaded to the module:
  - `Objects/PLC01` is a PackML base object after OPC 30050 (TagID, PackMLVersion, `Status`, `Admin`,
    `BaseStateMachine` with CurrentState and the methods Reset … Clear, `SetUnitMode(UnitMode)`). Which FMI variable
    is which PackML tag is configured in `opcua.servers.PLC01.packml_tags/packml_commands` of
    `godot/config/uns.json` (e.g. `Status.StateCurrent` = `packml_state`, `Admin.ProdDefectiveCount` = `parts_nok`).
  - All other FMI variables form the tag table `Program/Inputs|Outputs|Parameters` - the I/O image of the devices
    the PLC controls (light barriers, belt, inspection result, robot handshake, KLT counts).
  - `Commands/<variable>(Value)`: one method per writable variable of the registry (`packml_command`,
    `klt_exchange_command`, `auto_exchange`, `unit_mode_command`). Result = status code: Good (the CPU took the
    value), BadNotConnected (no CPU on the backplane), BadTimeout, BadTypeMismatch, BadNotExecutable.
  - One OPC UA event type per UNS event of the PLC (`PartInspectedEventType`, `PartSortedEventType`, fields
    Session, Seq and the event fields, typed from the FMI models), emitted by the `PLC01` object.
  - `Diagnostics`: CpuConnected, SessionId, ImageUpdates. Without CPU all process values have the status
    BadNoCommunication.
  - String NodeIds `ns=2;s=PLC01.<path>`. The NodeIds and namespace are deterministic, the namespace index is 2.
  - Only the structure follows OPC 30050: there is no PackML/DI type nodeset (scalars instead of the PackML
    structured data types, VF extensions such as `Admin.AlarmCode`, `Admin.ProdGoodCount`). Open issue O48.
- Why a separate process and not "Godot = OPC UA server": the process boundary is the same as in a real controller
  (CPU ↔ communication processor over the backplane), the OPC UA stack is a mature library instead of
  self-written GDScript, and the server can be restarted, secured (Keycloak phase) and inspected with standard
  tools independently of the simulation. The price is one more container and one more hop (see measurements).

**Edge connector** (`services/edge`, new service). It reads every AID that has an OPC UA *and* an MQTT interface
and pairs the affordances by name (the AID describes the same data point twice):
- property: OPC UA monitored item (sampling 0, queue 50, publishing interval = `telemetry.min_interval_s`, 100 ms)
  → retained UNS telemetry `{"v", "ts"}`, `ts` = SourceTimestamp (the simulation time base, as before);
- event: OPC UA event of the type in the form → UNS event (flat JSON, `seq` = the PLC's event counter);
- action: UNS command topic → OPC UA method call → UNS ack (`{"corr","accepted","reason","v","ts"}`).
Topics, payloads and QoS on the UNS are unchanged for all consumers (historian, MES, bridge, alarms, Node-RED).
The edge publishes only values with a good status and subscribes the command topics only while the server
delivers good values, so it never answers for a controller it cannot reach and never competes with Godot.
The notifier of an event type is found over the inverse `GeneratesEvent` reference of the type.

**Godot: mixed protocols, mode explicit.** `opcua.enabled` + `opcua.servers` in the registry say which controllers
are on the OPC UA path (today PLC01). For them the UNS gateway publishes no telemetry and events and subscribes no
commands; `PlcBackplane` takes over. `--vf-backplane=off` (or `opcua.enabled: false`) restores the direct MQTT
publishing (debug, broker-only setups), `--vf-backplane=tcp://host:port` overrides the address; with
`--vf-uns=off` the backplane is off too unless given explicitly (headless test runs never feed a running stack).
All other devices stay on MQTT: the robot controller (UR controllers offer MQTT/REST gateways), the assembly cell
(an IIoT-style cell controller), the KLT stations and the stack light publish directly. This mix - PLC on OPC UA,
smart devices on MQTT - is what current plants look like. Field devices of the PLC (CV01, LB01/02, QS01) keep their
own MQTT telemetry as device twins (their I/O image is also in the PLC's tag table).

**AID with an OPC UA interface (generated).** The provisioner adds `InterfaceOPCUA`
(`InterfaceTemplateForOPCUA` of AID 1.1) for every controller in `opcua.servers`, next to `InterfaceMQTT`:
- `EndpointMetadata.base` = server endpoint, `contentType` application/octet-stream (UA binary), security
  `opcua_channel_sc` (uav_securityMode None, uav_securityPolicy …#None) and `opcua_authentication_sc`
  (uav_userIdentityToken Anonymous) - the hook for the security phase.
- Forms use the AID 1.1 OPC UA terms: `href` = `?id=nsu=<namespace URI>;s=<identifier>` (expanded NodeId with
  the namespace URI, independent of the index) and `uav_browsePath` = `/0:Objects/2:PLC01/2:Status/2:StateCurrent`.
  Properties = all FMI outputs (as in the MQTT interface, so ADR-0013's rule holds for both); actions = the
  methods `Commands/<variable>` with input schema `Value`, `op` invokeaction, `synchronous` true (no ackForms: the
  status code of the call is the answer); events = the event types (`op` subscribeevent). `op` follows the
  project convention of ADR-0020 (the AID 1.1 template has no `op` term).
- The **AIMC stays on the MQTT interface**: the bridge keeps writing the AAS from the UNS. Reading OPC UA in the
  bridge would add a second source path for the same values; the UNS is the IT-side integration layer.

**Ops gateway over OPC UA.** The PLC01 Control Component endpoints now reference the OPC UA affordances
(`PackMLState`, `PackMLCommand`, `ContainerExchange`, `AutoExchange`) plus two new ones, `UnitMode` (property
unit_mode) and `UnitModeCommand` (action unit_mode_command). For an affordance whose interface base is `opc.tcp://`
the gateway calls the method (asyncua client, own event loop thread, automatic reconnect) and observes properties
as monitored items; MQTT command/ack stays for affordances of MQTT interfaces (controllers without OPC UA).
ExecutePackMLCommand/ExecuteSkill/ExchangeContainer/SetAutoExchange keep their inputs and outputs. Inside the
compose network `VF_OPCUA_ENDPOINTS=opc.tcp://localhost:4840=opc.tcp://plc-comm:4840` rewrites the AID address
(the AAS describes the asset as seen from the host).

**Unit modes (closes O35).** The PLC program got the input `unit_mode_command` and the output `unit_mode`
(1 Production, 2 Maintenance, 3 Manual; change accepted only in STOPPED, IDLE, ABORTED). Outside Production the
controller does not start by itself and AC01 releases no parts (the line can run empty, e.g. for a predictive
maintenance check). `ExecuteSkill` applies the requested mode through `UnitModeCommand` before running the skill and
rejects it with "stop the line first" in other states.

## Consequences
+ The OT side looks like a plant: PLC with an OPC UA server (browsable with UaExpert / asyncua), an edge connector,
  PackML methods; the AID describes the real southbound interface and is used at runtime by two services.
+ UNS consumers are unchanged; the training data-flow view shows PLC01 → OPC UA server → edge → broker while the
  backplane is linked.
+ Unit modes are applied (prerequisite for the maintenance phase).
− Two more containers and one more hop: PLC01 telemetry/events now take backplane → OPC UA subscription (100 ms
  publishing interval) → MQTT instead of a direct publish (measured in docs/architecture/runtime-ot-it.md).
− The address space is "OPC 30050 structured", not conformant (O48). Security is None/Anonymous (O49). The edge has
  no store-and-forward buffer: events during an MQTT outage are lost as before (O50 extends O17 to the edge).
− The backplane carries the simulation's session id to the PLC (a simulation concept, documented in uns.md).
