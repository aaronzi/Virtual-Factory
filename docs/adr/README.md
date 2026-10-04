# Architecture Decision Records

Format: short [MADR](https://adr.github.io/madr/)-style records. New ADR = next number, status `proposed` → `accepted`
(or `superseded by NNNN`).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-godot-mobile-renderer-jolt.md) | Godot 4.7, Mobile renderer, Jolt physics | renderer superseded by 0010 |
| [0002](0002-fmi3-aligned-device-models.md) | FMI-3-aligned device models in GDScript | accepted |
| [0003](0003-xr-ready-architecture.md) | XR-ready architecture without XR implementation | accepted |
| [0004](0004-ephemeral-instances-preloaded-static-aas.md) | Ephemeral workpiece AAS, preloaded static AAS | accepted |
| [0005](0005-ot-it-split-mqtt-uns.md) | OT/IT split via MQTT UNS and edge services | accepted |
| [0006](0006-composition-root-dependency-rules.md) | Composition root and measured dependency rules | accepted |
| [0007](0007-gut-for-gdscript-tests.md) | GUT for GDScript tests | accepted |
| [0008](0008-plc-program-as-fmu.md) | PLC program as an FMI co-simulation slave | accepted |
| [0009](0009-physical-transport-and-items.md) | Physical transport with Jolt rigid bodies | accepted |
| [0010](0010-compatibility-renderer-indoor-lighting.md) | Compatibility renderer as default; indoor lighting without baking | accepted |
| [0011](0011-template-based-aas-generation.md) | Template-based AAS generation from vendored IDTA templates | accepted |
| [0012](0012-control-component-packml-on-interface.md) | Control Components with PackML state on the asset interface | accepted, runtime use refined by 0020 |
| [0013](0013-aas-interfaces-generated-from-fmi.md) | AAS interface descriptions generated from FMI model descriptions | accepted |
| [0014](0014-godot-uns-gateway.md) | Godot UNS gateway with its own MQTT client | accepted, PLC01 path refined by 0024 |
| [0015](0015-aimc-bridge.md) | Own AIMC-driven bridge instead of the BaSyx DataBridge or Node-RED | accepted |
| [0016](0016-bpmn-orchestration.md) | BPMN orchestration on MES level with Operaton | accepted |
| [0017](0017-aas-operations-delegated.md) | Line commands as AAS Operations delegated to an operations gateway | accepted, topic resolution refined by 0020 |
| [0018](0018-in-world-training-ui.md) | In-world training UI: world-space panels, passive views, live AAS via events | accepted |
| [0019](0019-historian-timeseries-linked-segment.md) | Historian (InfluxDB 3 Core) referenced by IDTA TimeSeries LinkedSegments; slim AAS | accepted |
| [0020](0020-control-component-and-aid-drive-commands.md) | Control Component and AID configure the command and event paths | accepted |
| [0021](0021-item-level-dpp-basyx-dpp-api.md) | Item-level digital product passports served by the BaSyx Go DPP API | accepted |
| [0022](0022-grafana-dashboards-on-the-historian.md) | Grafana dashboards on the historian (SQL via Flight SQL), anonymous read-only | accepted |
| [0023](0023-discovery-registry-resolution-and-gs1-resolver.md) | AAS resolution via discovery and registry; GS1 Digital Link resolver and QR codes on the parts | accepted |
| [0024](0024-plc-opc-ua-server-and-edge-connector.md) | PLC01 on OPC UA: communication module, backplane link and edge connector | accepted |
| [0025](0025-service-decomposition-sustainability-erp.md) | Service decomposition: sustainability service, ERP order simulator, persistent passports | accepted |
| [0026](0026-alarm-management-isa-18-2-timescaledb.md) | Alarm management after ISA-18.2 in an alarms & events service on TimescaleDB | accepted |
| [0027](0027-optional-security-profile-keycloak-abac.md) | Optional secure profile: Keycloak, BaSyx Go ABAC, broker ACLs, OPC UA security | accepted |
| [0028](0028-supplier-environment-batch-aas-federated-footprints.md) | Supplier data exchange: second AAS environment, batch AAS and federated batch footprints | accepted |
| [0029](0029-predictive-maintenance-condition-monitoring.md) | Predictive maintenance: wear in the device models, RUL from the historian, maintenance orders in BPMN | accepted |
| [0030](0030-scalable-factory-visuals.md) | Scalable factory visuals: coherent presets, Blender finishes, revised performance targets | accepted |
