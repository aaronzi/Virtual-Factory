# AAS model of the Virtual Factory

> Status: M3. Built by the provisioner (`services/provisioner`) from **official IDTA submodel templates**
> (vendored in `aas/templates/idta`, fetched from the IDTA SMT repository) and **Virtual Factory custom templates**
> (`aas/templates/custom`), filled with asset data from `aas/data`. Output: one AASX per AAS (metamodel V3.0) in
> `infra/basyx/preload`, imported by BaSyx Go at startup. Each AASX is checked with basyx-python-sdk (strict) and
> the IDTA `aas-test-engines`.

## 1. Identifiers

| Kind | Pattern | Example |
|---|---|---|
| AAS | `https://virtual-factory.example/ids/aas/<TAG>` | `…/aas/RB01` |
| Asset (globalAssetId) | `…/ids/asset/<TAG>`; product type and workpieces: GS1 Digital Link (ADR-0021) | `…/asset/CV01`, `https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123` |
| Digital product passport id | = AAS id (item: workpiece AAS, model: PC3280_TYPE) | `…/aas/WP_PC3280_2026_000123` |
| Submodel | `…/ids/sm/<TAG>/<idShort>/<template major version>` | `…/sm/CV01/Nameplate/3` |
| Custom template / concept | `…/ids/smt/<Name>/<v>/<r>`, `…/ids/cd/<Template>/<Element>/<v>/<r>` | `…/cd/EnergyConsumption/ActualPower/1/0` |
| FMI process value concept | `…/ids/cd/fmi/<ModelName>/<variable>` | `…/cd/fmi/BeltConveyor/belt_speed` |
| Capability concept | `…/ids/capability/<Name>` (`aas/data/capabilities.yaml`) | `…/capability/InspectColour` |
| Workpiece serial | `PC3280-<YYYY>-<NNNNNN>` | `PC3280-2026-000123` |
| Supplier AAS / submodel (ADR-0028) | same patterns below the company's namespace `https://virtual-factory.example/<company>/ids` (`idBase` in the asset data) | `…/druckguss-pfalz/ids/aas/BATCH_DGP_260914_F` |
| Supplier product type / batch (globalAssetId) | GS1 Digital Link `…/01/<GTIN>` / `…/01/<GTIN>/10/<lot>` (AI 10 = batch) | `https://virtual-factory.example/01/04099991010019/10/DGP-260914-F` |

These patterns are how the provisioner and the MES **mint** ids. Clients do not build AAS or submodel ids from
them to read an AAS: they resolve them (next section).

## 1a. Identification and resolution (ADR-0023)

| Step | Service (BaSyx Go AAS environment, 8091) | Input → output |
|---|---|---|
| 1 | Discovery `GET /lookup/shells?assetIds=<b64url({"name":"globalAssetId","value":…})>` | asset id → AAS id(s). Specific asset ids (`serialNumber`, `manufacturerPartId`) work too; several `assetIds` must all match |
| 2 | AAS Registry `GET /shell-descriptors/<b64url(AAS id)>` | AAS id → descriptor: `globalAssetId`, `specificAssetIds`, endpoint (`AAS-3.2`, href), ids + endpoints of the submodels |
| 3 | Submodel Registry `GET /submodel-descriptors/<b64url(submodel id)>` | submodel id → idShort, semanticId, endpoint (`SUBMODEL-3.2`) |
| 4 | Repository at the descriptor's href | shell / submodel content, `$value`, `invoke`, attachments |

- **What a client knows**: devices and props have the asset id `…/ids/asset/<TAG>` (their type plate). The product
  type and the workpieces carry the GS1 Digital Link `https://virtual-factory.example/01/<GTIN>[/21/<serial>]`
  (QR code on the part label). The serial number also works as a specific asset id.
- Descriptors are written by the registry integration of the repository (`GENERAL_*REGISTRYINTEGRATION=true`),
  including the workpiece AAS of the MES. Endpoints use `GENERAL_EXTERNALURL` (`http://localhost:8091`). Services
  in the compose network rewrite this prefix to `http://aas-env:8091` (`VF_AAS_ENDPOINT_MAP`).
- Federation: clients take a **list** of environments (`VF_AAS_REGISTRIES`, Godot `aas_registries`) and use the
  first one that knows the id. Endpoints in descriptors may point to other hosts. The **supplier environment**
  (port 8191, `http://supplier-aas-env:8191` in compose, ADR-0028) is listed for the sustainability service and the
  Godot inspector; an unreachable environment is skipped, its error is raised only if no other one knows the id.
- Fallback (documented, Godot inspector only): an AAS that no registry knows is read from the own repository by
  its id. Concept descriptions have no registry and come from the own repository.
- Implementations: `vf_common.resolver.AasResolver` / `vf_common.registry_aas.RegistryAas` (Python),
  `connectivity/aas/aas_client.gd` (Godot). The GS1 Digital Link resolver (`services/resolver`, port 8096) uses
  the same chain: see [services.md](services.md#resolver).

## 2. Asset inventory

| Tag | Asset | Kind | derivedFrom | Manufacturer (asset) |
|---|---|---|---|---|
| PLANT01 | Plant 01 of VF Pneumatics (site, ISA-95 site/area) | Instance | – | VF Pneumatics GmbH |
| LINE01 | Inspection & sorting line | Instance | – | VF Automation Systems GmbH |
| PC3280_TYPE | Product type PC-32-80-DA-M (ISO 15552 cylinder Ø32 × 80) | Type | – | VF Pneumatics GmbH |
| CMP_* (9) | Purchased/manufactured components of the BoM | Type | – | VF Pneumatics / suppliers |
| *workpiece* | Product instance `PC3280-YYYY-NNNNNN` (created by the MES in M4; item-level DPP, ADR-0021) | Instance | PC3280_TYPE | VF Pneumatics GmbH |
| AC01 | Assembly & test cell AC-200 (black box) | Instance | – | VF Automation Systems GmbH |
| CV01 | Belt conveyor BC-3000 | Instance | – | VF Automation Systems GmbH |
| LB_TYPE / LB01, LB02 | Retro-reflective sensor LX12-R | Type / Instance | LB_TYPE | Lumetra Sensortechnik GmbH |
| QS01 | Colour inspection station QS-100 (true-colour sensor CX30) | Instance | – | VF Automation Systems GmbH |
| UR5E_TYPE / RB01 | Universal Robots UR5e | Type / Instance | UR5E_TYPE | Universal Robots A/S (public data sheet values) |
| GR01 | 2-finger parallel gripper PG-85 | Instance | – | VF Automation Systems GmbH |
| KLT_TYPE / KLTA01, KLTB01 | Small load carrier KLT 6428 on stand | Type / Instance | KLT_TYPE | VF Automation Systems GmbH (stand), VDA 4500 box |
| LC10_TYPE / PLC01 | Line controller LC-10 running the "SortingLine" PLC program | Type / Instance | LC10_TYPE | VF Automation Systems GmbH |
| SL01 | Stack light SL3-RAG-B on the control cabinet (driven by PLC01) | Instance | – | Lumetra Sensortechnik GmbH (fictional) |

**Supplier environment** (port 8191, data `aas/data/supplier/`, ADR-0028): company AAS of the four suppliers
(CompanyData, ContactInformations), the suppliers' product type AAS of the five purchased articles (DGP_EC32_F,
DGP_EC32_R, DTS_SK_PC32, NRN_4762_M5X16, KTW_SK53_RD: Nameplate, declared CarbonFootprint, material composition;
globalAssetId = Digital Link of the GTIN) and the batch AAS of delivered lots (§6c). The `CMP_*` AAS above are VF
Pneumatics' purchased-part view of the same articles (same `gtin` specific asset id).

Companies other than Universal Robots are **fictional**. The UR5e AAS is maintained by the plant operator and
uses public data sheet values nominatively; no logos are reproduced.

## 3. Submodels per asset

Legend: **I** IDTA template, **C** custom template (`aas/templates/custom`), **G** generated by the provisioner from
the FMI model description, the layout or the UNS registry.

| Submodel | Template | PLANT | LINE | PRODUCT TYPE | CMP | WORKPIECE | AC01 | CV01 | LB type / inst | QS01 | UR5e type / RB01 | GR01 | KLT type / inst | LC10 type / PLC01 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Nameplate | I 02006 3.0 | | ● | ● | ● | ● | ● | ● | ● / ● | ● | ● / ● | ● | ● / ● | ● / ● |
| TechnicalData | I 02003 2.0 | | | ● | ● | ● (as-built) | ● | ● | ● / | ● | ● / | ● | ● / | ● / |
| ContactInformations | I 02002 1.0 | ● | | ● | | ● | ● | | ● / | | ● / | | | ● / |
| HandoverDocumentation | I 02004 2.0 | | ● | ● | | ● (+ certificate) | ● | ● | ● / | ● | ● / | | | ● / |
| CarbonFootprint | I 02023 1.0 | | | ● (declared) | ● | ● (actual) | ● | ● | ● / | ● | ● / | ● | ● / | ● / |
| CompanyData | I 1.0 | ● | | | | | | | | | | | | |
| AssetLocation | I 1.0 (G) | ● | ● | | | ● | ● | ● | / ● | ● | / ● | | / ● | / ● |
| Models3D | I 1.0 (G) | | | ● | | | ● | ● | ● / | ● | ● / | | ● / | |
| HierarchicalStructures | I 02011 1.1 | ● (site) | ● (line) | ● (BoM) | | ● (as-built BoM) | | | | | / ● (robot cell) | | / ● (contents, G at runtime) | |
| CapabilityDescription | I 02020 1.0 | | ● | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| ControlComponentType | I 2.0 | | | | | | | | | | ● / | | | ● / |
| ControlComponentInstance | I 2.0 | | | | | | | | | | / ● | | | / ● |
| ProcessParameters | I 02031 1.0 | | | ● | | | | | | | | | | |
| ManufacturingRecipe | C 1.1 | | | ● | | | | | | | | | | |
| LineControl (Operations) | C 1.2 | | ● | | | | | | | | | | | |
| DppMetadata | I 1.0 | | | ● (model) | | ● (item) | | | | | | | | |
| ProductMaterialComposition | C (from DBP) | | | ● | ● | ● (+ batches) | | | | | | | | |
| ProductCircularity | C (from DBP) | | | ● | | ● (per lot) | | | | | | | | |
| ExecutedProcesses | I 1.0 | | | | | ● | | | | | | | | |
| QualityInspection | C | | | | | ● | | | | | | | | |
| MeasurementValue | I 1.0 | | | | | ● (×2) | | | | | | | | |
| AssetInterfacesDescription | I 1.1 (G) | | | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| AssetInterfacesMappingConfiguration | I 2.0 (G) | | | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| OperationalData | C (G) | | | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| EnergyConsumption | C (G + static) | | ● | | | | ● | ● | / ● | ● | / ● | | | / ● |
| TimeSeries (LinkedSegment → historian) | I 1.1 (G) | | | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| SimulationModels | I 1.0 (G) | | | | | | ● | ● | / ● | ● | / ● | | / ● | / ● |
| Reliability | I 1.0 | | | | | | | | ● / | ● | | ● (+ observed, runtime) | | |
| FunctionalSafety | I 1.0 | | | | | | ● | | | | ● / | | | |
| MaintenanceInstructions | I 1.0 | | | | | | | ● | | | ● / | ● | | |
| ConditionMonitoring | C 1.0 | | | | | | | | | | | ● (runtime values) | | |
| SoftwareNameplate | I 1.0 | | | | | | | | | | / ● | | | ● / ● |
| ProcessVariablesForManufacturingKPICalculation | I 02066 1.0 | | ● | | | | | | | | | | | |
| ProductionCalendar | I 02067 1.0 | | ● | | | | | | | | | | | |
| DataRetentionPolicies | I 1.0 | | ● | | | | | | | | | | | |

Rationale for the main choices:

- **Product passport (DPP/DBP):**
  - DppMetadata, Nameplate, TechnicalData, CarbonFootprint and HandoverDocumentation come from IDTA.
  - Material composition and circularity use custom generalisations of the DBP templates. The DBP versions contain
    battery-only mandatory elements (battery chemistry, extinguishing agents). The custom versions keep the DBP element
    names, drop the battery prefix, and add durability/repairability as required by ESPR.
- **Recipe:** IDTA 02031 *Process Parameters* (per-process parameters for product, process and resource) and the
  custom ISA-88 *ManufacturingRecipe* (sequencing, required capabilities, formula) describe the same process
  (OP10–OP90) for comparison. See §6.
- **Control Component Type/Instance 2.0:** offered by the PLC program and the robot.
  - The runtime execution state (PackML) lives on the interface: the AID properties `packml_state`, `unit_mode`
    and the actions `packml_command`, `unit_mode_command` (PLC01: OPC UA interface, ADR-0024).
  - The Control Component Instance references these via `Endpoints`. This follows Control Component 2.0, which keeps
    runtime state out of the submodel.
  - PLC01 endpoints (contract with the ops gateway, ADR-0020/0024), all in `InterfaceOPCUA`: `PackMLState` →
    property `packml_state`, `PackMLCommand` → action `packml_command`, `UnitMode` → property `unit_mode`,
    `UnitModeCommand` → action `unit_mode_command` (interface PackML); `ContainerExchange` → action
    `klt_exchange_command`, `AutoExchange` → action `auto_exchange` (interface `ContainerHandling` of LC10_TYPE).
    The robot's endpoints stay in its MQTT interface.
  - Each skill instance has an extra list `UsesEndpoints` (ReferenceElements → `Endpoints.<name>`), because Control
    Component 2.0 has no skill → endpoint relation: Produce → PackMLCommand, PackMLState, AutoExchange;
    ExchangeContainer → ContainerExchange. Skills, modes and parameters are enforced at runtime by
    `LINE01/LineControl/ExecuteSkill` (services.md).
- **Interfaces:** the AID (MQTT, UNS topics from `godot/config/uns.json`; for controllers with an OPC UA server
  also `InterfaceOPCUA`, ADR-0024) and the AIMC mapping (MQTT AID property → OperationalData/EnergyConsumption
  element, with JSON lookup transformations) are *generated* from the FMI model descriptions. At runtime the AAS is
  the configuration: the bridge reads AIMC + AID properties, the ops gateway the AID affordances behind the Control
  Component endpoints, the MES the AID events of the MQTT interfaces, the edge connector pairs the OPC UA and MQTT
  affordances of each AID by name (ADR-0015, ADR-0020, ADR-0024). The AIMC stays on the MQTT interface.
- **AID actions and events** (open collections, generated, ADR-0020):

  | Element | Content |
  |---|---|
  | `title`, `synchronous` | description; `false` (the result arrives on the ack topic, not on the request) |
  | `input` (td:hasInputSchema) | object schema, `properties.Value/CorrelationId/Source` with `key` = `v` / `corr` / `source` |
  | `output` (td:hasOutputSchema) | acknowledgement payload: `CorrelationId/Accepted/Reason/Value/Timestamp` → `corr` / `accepted` / `reason` / `v` / `ts` |
  | `forms` | `op` = `invokeaction`, `href` = `/{root}/{device}/cmd/{variable}`, contentType, security, `mqv_qos` 1, `mqv_retain` false, `mqv_controlPacket` publish |
  | `ackForms` | second TD form (semanticId td:hasForm): `op` = `queryaction`, `href` = `/{root}/{device}/cmd-resp/{variable}`, QoS 1, not retained, `mqv_controlPacket` subscribe |
  | event `forms` | `op` = `subscribeevent`, `href` = `/{root}/{device}/event/{event}`, QoS 1, subscribe |

  AID 1.1 maps a single form per affordance; `ackForms` is the documented extension for the second form (TD 1.1
  allows several forms told apart by `op`). Consumers that ignore it still see a valid `forms`.
- **AID OPC UA interface** (`InterfaceOPCUA`, AID 1.1 `InterfaceTemplateForOPCUA`, generated by
  `provisioner/interfaces_opcua.py` from the same address-space model as the server, ADR-0024):

  | Element | Content |
  |---|---|
  | `EndpointMetadata` | `base` = `opc.tcp://localhost:4840/vf/plc01`, `contentType` application/octet-stream (UA binary), `security` → `opcua_channel_sc` (`scheme` ua_channelsec, `uav_securityMode` None, `uav_securityPolicy` …/SecurityPolicy#None) and `opcua_authentication_sc` (`scheme` ua_authentication, `uav_userIdentityToken` Anonymous); secure profile (ADR-0027, `VF_SECURITY_PROFILE=secure`): `uav_securityMode` SignAndEncrypt, `uav_securityPolicy` …/SecurityPolicy#Basic256Sha256, `uav_userIdentityToken` UserName - and the MQTT interface `basic_sc` (`scheme` basic) instead of `nosec_sc` |
  | properties | every FMI output (same set as the MQTT interface): `type`, `title`, `unit`, `observable`; `forms.href` = `?id=nsu=urn:virtual-factory:plant01:line01:plc01;s=PLC01.Status.StateCurrent`, `forms.uav_browsePath` = `/0:Objects/2:PLC01/2:Status/2:StateCurrent` |
  | actions | every writable variable: method `PLC01.Commands.<variable>`; `synchronous` true (result = status code of the call, no `ackForms`), `input.properties.Value` (`key` = argument name `Value`), `forms` with `op` invokeaction, `href`, `uav_browsePath`; the object of the call is the parent of the method (`PLC01.Commands`) |
  | events | `forms.href` = the event type (`?id=nsu=…;s=PartSortedEventType`), `op` subscribeevent, `uav_browsePath` `/0:Types/0:EventTypes/0:BaseEventType/2:PartSortedEventType`; the notifier (`PLC01`) is found over the inverse `GeneratesEvent` reference |

  `href` uses the expanded NodeId with the namespace URI (`nsu=`), so it does not depend on the namespace index;
  the browse path uses index 2, which `plc-comm` guarantees (it warns otherwise). Example (packml_state):

  ```json
  {"idShort": "packml_state", "type": "integer", "title": "PackML state (ISA-TR88: 2 Stopped, 4 Idle, …)",
   "observable": true, "forms": {"href": "?id=nsu=urn:virtual-factory:plant01:line01:plc01;s=PLC01.Status.StateCurrent",
   "security": ["→ opcua_channel_sc", "→ opcua_authentication_sc"],
   "uav_browsePath": "/0:Objects/2:PLC01/2:Status/2:StateCurrent"}}
  ```

- **Process values (slim AAS, ADR-0019):** every FMI output gets a concept description (unit, definition) and is
  described in the AID, but the AAS stores only **state and slow values**: OperationalData process values and AIMC
  mappings exist for outputs with FMI variability `discrete` (Boolean/Int32/String and per-event Float64 values such
  as QS01 `r/g/b/hue/delta_e`, AC01 `last_leak_rate`), plus OperatingState, OperatingHours and the
  EnergyConsumption values. Continuous signals (UR5e joints/TCP/gripper width, CV01 belt speed/position, AC01
  cycle progress) live only in the historian.
- **History:** one IDTA TimeSeries 1.1 per device, generated from the model description: `Metadata.Record` =
  `Time` (semanticId `https://admin-shell.io/idta/TimeSeries/UtcTime/1/1`, `xs:dateTime`) + one Property per FMI
  output (idShort = variable = database column, semanticId = its FMI concept description with unit), without
  values; `Segments.LinkedSegment` `Historian` with `Endpoint` (InfluxDB SQL endpoint, host view) and `Query`
  (SQL, last hour). The UtcTime concept description is added by the provisioner with the texts of IDTA 02008-1-1
  Table 10 (not published in the SMT repository). Static: nothing writes into it at runtime.
- **Energy:** no IDTA template exists for measured consumption, hence the custom EnergyConsumption (rating, actual
  power, energy, compressed air, operational CO₂e with an emission factor); its `TimeSeries` element references the
  device's TimeSeries submodel.

## 4. Process steps (shared by recipe, process parameters, executed processes)

| Step | Name | Resource | Capability | Planned time |
|---|---|---|---|---|
| OP10 | Pre-assemble piston and rod | AC01 | AssembleCylinder | PT2S |
| OP20 | Insert seals | AC01 | AssembleCylinder | PT1.5S |
| OP30 | Insert piston assembly into barrel | AC01 | AssembleCylinder | PT1.5S |
| OP40 | Mount end caps, tighten screws (6 Nm) | AC01 | AssembleCylinder | PT2.5S |
| OP50 | Leak test (6 bar, pressure decay, ≤ 1.0 cm³/min) | AC01 | LeakTest | PT2S |
| OP60 | Function test (stroke time 0.28–0.36 s at 6 bar) | AC01 | FunctionTest | PT1.5S |
| OP70 | Fit protective cap (red PE) | AC01 | FitProtectiveCap | PT1S |
| OP75 | Transport to inspection | CV01 | Transport | PT11S |
| OP80 | Colour inspection of the protective cap (ΔE76 ≤ 25 vs. sRGB 0.78/0.08/0.10) | QS01 | InspectColour | PT0.5S |
| OP90 | Sort and pack (KLT A good, KLT B reject; 12 per KLT) | RB01 | PickAndPlace, Sort | PT7S |

## 5. Shared facts (keep consistent across all asset data)

- Plant: VF Pneumatics GmbH, Fabrikstraße 1, 67655 Kaiserslautern, DE (fictional). Hall 1, area *Final Assembly*,
  line LINE01. Machine builder: VF Automation Systems GmbH, Fabrikstraße 3 (fictional). Sensors: Lumetra Sensortechnik
  GmbH, Lichtweg 5, 79111 Freiburg (fictional).
- Commissioning of the line: 2025-09-15. Assets manufactured in 2025 unless noted. CE conformity of machines built in
  2025: Machinery Directive 2006/42/EC (Regulation (EU) 2023/1230 applies from 2027-01-20).
- Document classes: VDI 2770:2020 (e.g. 02-01 technical specification, 03-02 operation, 02-04 certificates/declarations).
- Reliability template: MTTF/MTBF values in **years** (unit of the concept description). Only where a figure is
  published (LB_TYPE, QS01); the UR5e has no public MTTF, so no Reliability submodel rather than a guessed value.
- PLANT01 is a site, not a product: CompanyData + ContactInformations instead of a Nameplate.
- Grid emission factor 0.363 kg CO₂e/kWh (`common/energy_defaults.yaml`).
- Product PC-32-80-DA-M:
  - Mass 0.59 kg. Declared PCF (A1–A3) 4.2 kg CO₂e per piece (ISO 14067).
  - Operating pressure 1–10 bar. Temperature −20…80 °C. Thread M10×1.25. Double-acting, magnetic piston, adjustable
    pneumatic cushioning.
  - Takt 12 s.
- Electrical ratings (EnergyConsumption):

  | Asset | Rating |
  |---|---|
  | AC01 | 300 W idle, 1.2 kW working, 400 V 3~ 16 A, compressed air 5 Nl per part at 0.12 Wh/Nl |
  | CV01 | 0.18 kW gear motor with VFD, 8 W standby |
  | LB | 1.2 W at 24 V DC |
  | QS01 | 2.5 W sensor + 4 W ring light, 24 V DC |
  | RB01 | 90 W powered idle, typical 200 W, max 570 W, 100–240 V AC |
  | PLC01 | 25 W, 24 V DC |

- UR5e (public data sheet):
  - Payload 5 kg, reach 850 mm, 6 DOF, repeatability ±0.03 mm (ISO 9283), weight 20.6 kg, footprint Ø149 mm.
  - All joints ±360° at 180°/s. TCP speed 1 m/s. IP54. Ambient 0–50 °C. Noise < 65 dB(A).
  - Power typical 200 W, max 570 W.
  - 17 configurable safety functions, PLd Category 3 (EN ISO 13849-1).

## 6. Recipe representations (IDTA 02031 and custom ISA-88 recipe, M4: complementary roles)

Both describe OP10–OP90, but since M4 each has its own job and they reference each other instead of duplicating
values:

| Aspect | Process Parameters (IDTA 02031) | ManufacturingRecipe 1.1 (custom, ISA-88) |
|---|---|---|
| Role | **Setpoints**: product/process/resource parameters per process (single source of the values) | **Structure and acceptance**: header, formula limits, equipment requirements, procedure |
| Sequencing | Not modelled | `Sequence`, `Predecessors`, executable **procedure model** (`Procedure/ProcedureModel` = `bpmn/workpiece_lifecycle.bpmn`) |
| Links | – | `Parameter/ProcessParameterReference` → the setpoint element; `Step/ProcessReference` → the process; `Step/ExecutionElement` → BPMN task that executes/records the step |
| Resource assignment | Resource parameters (concrete resource) | Required **capabilities**, optional candidate resource |
| Life cycle | Submodel versioning only | Recipe version, approval status, valid-from |
| Runtime use | Same structure as ExecutedProcesses of the instance | MES: limits for the quality verdict; Operaton: procedure model |

`NominalValue` is kept only where no single setpoint element exists (composite reference colour, stroke time
nominal between min/max).

## 6a. Runtime submodels (M4)

- **Workpiece instance AAS** grow along the process (stages released → inspected → packed, or lost); structure from
  `aas/data/blueprints/workpiece_instance.yaml`, see [services.md](services.md#mes). Thumbnail: link to the product
  type's thumbnail (no copy per part). Each one is the item-level digital product passport of its part (§6b).
- **KLT contents** (KLTA01/KLTB01 `HierarchicalStructures`, archetype OneDown): station → `Box` (KLT on the station,
  CoManagedEntity) → one Node per packed workpiece (`globalAssetId` = the workpiece's GS1 Digital Link) + `HasPart`.
  Cleared on exchange.
- **Submodel ownership** (ADR-0025): the MES creates the workpiece AAS and writes all its submodels except the
  CarbonFootprint, which the sustainability service writes (BPMN task `pcf-calculate` after packing) and references
  from the shell; the MES keeps that reference when it replaces the shell. KLT contents, LINE01 KPIs: MES.
  EnergyConsumption derived values: sustainability service. OperationalData/OperatingState: bridge (AIMC).
  GR01 ConditionMonitoring and the observed Reliability sets: maintenance service (§6d, ADR-0029).
- **Instance PCF** (ISO 14067 terminology, production-based, R9; sustainability service `carbon.py`,
  `process_energy.py`), computed when a part is packed, static inputs from the AAS, energy from the historian (UNS
  series are step functions):
  1. *Material (A1)*: Σ BulkCount × PCF of the component batch built into the part, from a `SupplierFootprints`
     source per BoM node and batch: first the **supplier batch AAS** (purchased components: GTIN of the component
     type AAS + lot → batch Digital Link → federated discovery → CarbonFootprint of the batch, primary data,
     ADR-0028), else the declared PCF of the component type AAS (found via the `globalAssetId` of the type's BoM;
     in-house components and batches without supplier record, secondary data).
  2. *Assembly cell* (one part at a time): ∫ P_AC01 dt over the part's cycle, from the previous release to its
     release (idle, blocked and held time included, at most 30 min), entirely to this part. AC01 `power` contains
     the compressed-air equivalent, so the air share E_air = ΔAirConsumed in the cycle × `SpecificEnergy` (AC01
     EnergyConsumption, 0.12 Wh/Nl) is split off and reported separately (not added twice).
  3. *Downstream devices* (CV01, LB01, LB02, QS01, RB01, SL01): ∫ P_d(t) / n(t) dt from release to sort, with
     n(t) = AC01 `release_count` − PLC01 `sorted_count` (parts in process). Energy while no part is on the line
     is allocated to no part (it remains in LINE01 `OperationalCO2eq`).
  4. *Energy CO₂e* = (electricity + compressed air) × emission factor of LINE01 (0.363 kg/kWh).
  5. *Production losses* (rejects, packed into KLT B): a reject reports its own footprint (components + energy,
     marked as production loss in the description of its first entry); every good part carries L / G - L =
     cumulative footprint of the session's rejects, G = cumulative good parts including itself, at packing time.
     Transparent and converges to the exact allocation L_total / G_total for a stationary reject rate; a restart of
     the sustainability service resets L and G.
  6. *CarbonFootprint* (template-conformant list `ProductCarbonFootprints`): entry 1 `A1-A3` = total, entry 2
     `A1` = components, entry 3 `A3` = energy CO₂e + losses with the extra properties `ElectricalEnergy` (kWh,
     without air), `CompressedAirEnergy` (kWh), `ProductionLossCO2eq` (kg) and `LineResidenceTime` (s) (generated
     concept descriptions with units). Entries 2 and 3 break entry 1 down and must not be added to it.
  7. Without the historian: line energy per part (rolling 5 min of the AAS energy counters), method "fallback".
  8. *Data quality* (PACT concept; CarbonFootprint 1.0 has no elements for it, so extra properties with generated
     concept descriptions): `PrimaryDataShare` (%) on entry 1 (A1-A3) and entry 2 (A1) = emissions-weighted share
     of primary data - per supplier batch its declared primary data share, type averages count 0, A3 (measured
     energy and losses of LINE01) counts 100; `SupplierSpecificDataShare` (%) on entry 2 = share of A1 taken from
     supplier batch footprints. Per component the service reports `dataQuality` (`primary`/`secondary`) on
     `/api/footprints`.
  The declared type PCF (4.2 kg) additionally covers upstream manufacturing at suppliers.
- **EnergyConsumption** (devices + LINE01 totals): `OperationalCO2eq`, `LastUpdate`, `MeasurementStart` (session start)
  maintained by the sustainability service; `TimeSeries` references the device's TimeSeries submodel (history in the
  historian, see §3; the MES no longer writes time-series records).
- **LINE01 KPIs** (02066): production, busy, delay (Suspended) and down time from PackML state durations; good,
  inspected, produced, scrap quantities from the PLC counters.
- **AIMC transformations** are Lua (`aimc_main(sources)`, template-conformant), e.g. PackML state number →
  `OperatingState` name.

## 6b. Item-level digital product passport (ADR-0021)

Every workpiece AAS is a self-contained passport of its part, readable through the BaSyx Go DPP API
([services.md](services.md#dpp-api)):

- **Ids:** DPP id = AAS id; `uniqueProductIdentifier` = `globalAssetId` = GS1 Digital Link
  `https://virtual-factory.example/01/04099999032808/21/<serial>` (the DPP API resolves products by globalAssetId);
  `granularity` Item; `dppStatus` Inactive while in production and for rejects and lost parts, Active once a good
  part is packed (shipped); Archived reserved for the end of life. The type PC3280_TYPE is the model-level
  passport (DPP id = type AAS id, product id `…/01/04099999032808`, granularity Model).
- **Content** (`contentSpecificationIds`, only submodels present at the current stage): Nameplate, TechnicalData,
  ContactInformations, HandoverDocumentation, CarbonFootprint, HierarchicalStructures, ProductMaterialComposition,
  ProductCircularity, ExecutedProcesses, QualityInspection. MeasurementValue is not listed (two submodels with
  the same semanticId - the DPP API shows only one per semanticId; the values are in QualityInspection),
  AssetLocation neither (logistics, not passport data). CarbonFootprint is listed from the packed stage on and
  written by the sustainability service.
- **Retention** (LINE01 DataRetentionPolicies, ADR-0025): `ProductPassportShippedUnits` - passports of shipped units
  stay on the AAS server across sessions (P10Y, served by the DPP API); `ProductInstanceSessionData` - units not
  shipped (in production, rejected, lost) only for the current session. Serial numbers (and with them AAS ids and
  Digital Links) are never reused: the AC01 serial counter is retentive in live sessions.
- **Type data** come from `aas/data/common/product_passport_pc3280.yaml`, included by type and blueprint as named
  fragments (`$include: "common/product_passport_pc3280.yaml#Documents.DS"`), so both stay identical.
- **TechnicalData (as-built):** the type sections plus section `AsBuilt`: DateOfManufacture, MeasuredLeakRate,
  MeasuredStrokeTimeAdvance/Retract, MeasuredColourLab, MeasuredDeltaE76 (same concepts as in ExecutedProcesses).
  The line does not weigh the parts or set the cushioning; mass and cushioning stay type values.
- **ContactInformations:** Manufacturer (AAS927 administrative), AfterSalesService (AAS931 technical), TakeBack
  (AAS929 other contact, end-of-life take-back; also on the type).
- **HandoverDocumentation:** good parts get the *inspection certificate 3.1 (EN 10204 style)* `IC-<serial>`
  (VDI 2770 02-04, generated PDF, ~7 KB, sample `aas/files/docs/IC-PC3280-2026-000123.pdf`), followed by the type
  documents DS (02-01), OM (03-01/03-02), RI (03-05/03-06) and the REACH Art. 33 information SVHC-PC3280 (02-04;
  lead in brass and die-cast alloy, SCIP number, why the cylinder carries no CE marking). Files are uploaded as
  attachments; BaSyx deduplicates identical content (SHA-256 + size), so the type documents are stored once.
- **Material composition / circularity:** type entries plus `MaterialLocation.BatchId` resp. `ComponentId` +
  `BatchId` per recycled-content entry (optional elements of the custom templates). Recycled shares per lot =
  supplier lot certificate, simulated within ±15 % of the declared average.

**As-built BoM (IDTA 02011-1-1 HierarchicalStructures 1.1, ArcheType Full).** Same node idShorts and BulkCounts as
the type BoM (the sustainability service reads the type BoM for the component footprints):

```text
EntryNode (SelfManagedEntity, globalAssetId = Digital Link of the part)
├─ Barrel (CoManagedEntity, displayName "Barrel, batch L2609-0419")
│    BulkCount 1 · BatchId L2609-0419 · SameAs → PC3280_TYPE/HierarchicalStructures/EntryNode.Barrel
├─ EndCapFront (SelfManagedEntity, globalAssetId …/01/04099991010019/10/DGP-260914-F → supplier batch AAS)
│    BulkCount 1 · BatchId DGP-260914-F · SameAs → PC3280_TYPE/HierarchicalStructures/EntryNode.EndCapFront
├─ …  (9 nodes)
└─ HasPart_Barrel … (EntryNode → node)
```

- A node stands for the **component batch** built into this unit. HS 1.1 uses SelfManagedEntity for assets with
  their own AAS and CoManagedEntity for parts managed only inside this submodel:
  - **purchased batches** (EndCapFront, EndCapRear, SealKit, ScrewM5x16, ProtectiveCap) have their own batch AAS
    in the supplier environment (ADR-0028): **SelfManagedEntity**, globalAssetId = batch Digital Link
    `https://virtual-factory.example/01/<GTIN of the supplier article>/10/<lot>`. The MES composes it from the
    GTIN and the lot (like a scan of the container's GS1-128 label), independent of the supplier environment's
    availability; clients resolve it via federated discovery (inspector: *Open asset AAS*).
  - **in-house lots** (`L<YYWW>-n`: barrel, piston rod, piston, cushioning screws) have no AAS:
    **CoManagedEntity**; AASd-014 forbids globalAssetId/specificAssetIds there.
- Every node keeps the statement `BatchId` (generated concept description) and a `SameAs` relationship to the type
  BoM node, which is SelfManaged with the component type's globalAssetId (CMP_* AAS).
- Rejected alternative: SelfManaged nodes with the component type's globalAssetId and specificAssetId `batchId`.
  This would claim that the batch is the asset of the CMP AAS, i.e. a type, not a batch.
- Traceability query (all parts containing a batch): [services.md](services.md#traceability-which-parts-contain-a-batch).

## 6c. Supplier batch AAS (ADR-0028)

Created by the supplier portal (`services/supplier`) in the supplier environment when a lot is despatched (the ERP
asks for the despatch advice when the MES reports the lot staged at the line); blueprint
`aas/data/supplier/blueprints/batch_instance.yaml`, values per lot from `aas/data/supplier/batch_profiles.yaml`.

| Element | Content |
|---|---|
| AAS | `<company idBase>/aas/BATCH_<lot>`, assetKind Instance, derivedFrom the supplier's product type, globalAssetId `…/01/<GTIN>/10/<lot>`, specific asset ids `manufacturerPartId`, `batchId`, `customerPartId` |
| BatchInformation (custom, YAML DSL) | BatchId, ManufacturerPartId, CustomerPartId, ProductType (reference to the type AAS), Quantity, DateOfManufacture, ProductionSite, Customer, DespatchAdviceNumber, DespatchDate, MaterialCertificate, MeanMassPerPiece, RecycledContent (pre/post-consumer %, metal parts only) |
| CarbonFootprint (IDTA 1.0) | one entry per piece, A1-A3, ISO 14067 + PACT methodology; PcfCO2eq of this batch (declared × (1 ± spread) − credit × Δ recycled share); extra properties `PrimaryDataShare` (%), `BatchId` |
| ProductMaterialComposition (custom) | composition of the type scaled to the measured mean mass, `MaterialLocation.BatchId` = lot |
| HandoverDocumentation (IDTA 2.0) | inspection certificate 3.1 (EN 10204) `MC-<lot>` (VDI 2770 02-04), generated PDF (sample `aas/files/supplier/MC-DGP-260914-F.pdf`) |

Recycled shares per lot are computed with `vf_common.lot_values.recycled_share` - the MES writes the same values
into the passport's ProductCircularity (`RecycledContentInformation`, BatchId), so passport and batch AAS agree.

## 6d. Predictive maintenance (ADR-0029)

Component GR01 (gripper fingers, measured by the robot FMU RB01: `finger_wear`, `grip_force`, `grip_close_time`,
`grip_cycles`, `grasp_retries`, `gripper_fault`). Ownership: provisioner = manufacturer data, maintenance service =
condition, prognosis and field data.

| Submodel | Content | Written by |
|---|---|---|
| Reliability (IDTA 1.0, IEC 62683) | `NumberOfReliabilitySets`; `ConditionsGripperUnit` / `CharacteristicsGripperUnit` (24 V DC, useful life 10 million operations, MTTF 150 000 h, B10 10 million); `ConditionsFingerSet` / `CharacteristicsFingerSet` (finger set FS-PG85-V50, useful life 2.5 million grips, B10 2 million; end of life = 1.0 mm jaw offset) | provisioner (design) |
| | `ConditionsFingerSetObserved` / `CharacteristicsFingerSetObserved`: mean achieved grips per finger change (`UsefulLifeInNumberOfOperations`), B10 from a Weibull wear-out model (shape 3 assumed), number of changes in `OtherOperatingConditions`; `NumberOfReliabilitySets` 3 | maintenance service (after each change) |
| MaintenanceInstructions (IDTA 1.0) | `FingerChange` = MI-PG85-01 "Replace gripper fingers": condition-based (interval value = B10 2 000 000 cycles), alarm values 80 % warning / 100 % limit, safety, 1 technician, 20 min, steps 10 secure cell, 20 remove fingers (hex key), 30 fit FS-PG85-V50 at 6 Nm (torque wrench, spare part), 40 confirm finger change and test; spare part and tool lists | provisioner; read by the maintenance service (task text of the BPMN user tasks) |
| ConditionMonitoring (custom, `aas/templates/custom/ConditionMonitoring.yaml`) | `HealthState`, `HealthIndex`, `HealthIndicator` (IndicatorName `RB01.finger_wear`, CurrentValue, LimitValue 0.001, IndicatorUnit m, DataSource → RB01/TimeSeries), `RemainingUsefulLife` (RulCycles, RulCyclesLowerBound, RulHours, RulHoursLowerBound, PredictedFailureDate, Confidence, Method TrendFit/DesignRate, DataPoints, Throughput, OrderThreshold), `Symptoms` (GripForce, GripCloseTime, GraspRetries, GripCycles), `Recommendation` (en/de), `MaintenanceInstruction` (→ MaintenanceInstructions#FingerChange), `OpenMaintenanceOrder`, `MaintenanceRecords` (MaintenanceOrderId, MaintenanceID, CompletedAt, Technician, Findings, PartsReplaced, CyclesAtMaintenance, HealthIndexBefore, Downtime), `LastUpdate` | provisioned initial state; values only by the maintenance service (changed values each 10 s, records after an order) |

Executed maintenance is recorded in `MaintenanceRecords`, not in ExecutedProcesses (that template describes the
production steps a product went through). The history of health index and RUL is in the historian (table
`maintenance`), not in the AAS (ADR-0019). Line control used by the maintenance order: LineControl `SetUnitMode`
(revision 1.2) and the skill `Maintain` of PLC01/ControlComponentInstance (endpoint `GripperMaintenanceReset` →
RB01 AID action `gripper_maintenance_reset`).

## 7. Asset data format (`aas/data/assets/<TAG>.yaml`)

See `services/vf_common/src/vf_common/aas/environment.py` and `instantiate.py`. In short:

- `tag`, `idShort`, `kind`, `assetType`, `displayName`, `description`, `derivedFrom`, `thumbnail`,
  `specificAssetIds`, `globalAssetId` (optional, default `…/ids/asset/<TAG>`; also used by `${asset:TAG}`),
  `idBase` (optional id namespace of another organisation, e.g. a supplier in `aas/data/supplier/`; replaces
  `https://virtual-factory.example/ids` in the AAS, asset and submodel ids of that asset, ADR-0028).
- `model3d: {file, preview, title, objectType}` generates Models3D.
- `device: {modelDescription, energy: {power, energy, air}, operatingHours, state: {variable, map, initial}}`
  generates AID, AIMC, OperationalData, SimulationModels and TimeSeries (LinkedSegment, endpoint and database from
  `infra/historian.json`); EnergyConsumption (dynamic part) only when `energy.power` names a live power output
  (PLC01 and the KLT stands have none).
- `location: false | [x, y, z]` (default: the position from the layout), `locationDescription` (text or en/de),
  `locationTime` (ISO 8601; default commissioning date) generate AssetLocation.
- `thumbnail: repo:<path>` (embedded) or `{path: <absolute URL>, contentType}` (runtime AAS linking an existing image).
- Tag `SELF` in `${asset:SELF}` / `sm:SELF/...` refers to the asset being built (shared files such as
  `common/machine_klt_instance.yaml`).
- Operations: `{_delegation: <URL>}` adds the BaSyx `invocationDelegation` qualifier (LINE01 LineControl → ops gateway).
- Extra ReferenceElements (`"+X": {modelType: ReferenceElement, value: {ref: <key>}}`) and extra SubmodelElementLists
  of them resolve `ref` keys like template ReferenceElements (e.g. `UsesEndpoints`,
  `common/control_uses_endpoints.yaml`).
- Extra elements `"+Name": {valueType, value, unit, description, conceptName?, semanticId?}`: the **unit belongs in
  `unit`, never in the description text**. Without an explicit `semanticId` the builder generates an IEC 61360
  concept description `<ID_BASE>/cd/property/<Name>` (preferred name/definition from the description, data type
  from the valueType, unit). One concept per name: the same name with another unit is a build error (use
  `conceptName` to separate concepts); a name used with several value types gets one concept per type
  (`.../property/Min/int`). Units are only allowed on numeric values (IEC 61360) - split values like "32 H9"
  into a number (mm) and a text property (tolerance class).
- Template semantic ids without a concept description in the IDTA library (ECLASS IRDIs of AssetLocation, the
  generic ArbitraryProp) get a concept description derived from the template element (`TEMPLATE_UNITS` adds
  units, e.g. ° for latitude/longitude). A test asserts that every Property/Range resolves to a concept
  description, measures have a unit and numeric values have numeric data types.
- `submodels: [{template: <Name-ver>, idShort?, values}]`. Values are keyed by idShort:
  - collections are maps, lists are lists
  - repeated/placeholder elements (`X__00__`) are lists, with an optional `_idShort` per item
  - `+Name: {...}` adds an element that is not in the template
  - `{ref: "aas:TAG" | "sm:TAG/IdShort#path" | "global:IRI"}` for references
  - `_noValue: true` in a Property dict (`{valueType, semanticId, _noValue: true}`) or an extra element gives a
    Property without value (structure only, e.g. the TimeSeries `Metadata.Record` definition)
  - `${asset:TAG}` / `${aas:TAG}` / `${sm:TAG/IdShort}` in strings
  - `_idShort`, `_displayName`, `_description`, `_semanticId` override the template values of any element
  - Entities (BoM / HierarchicalStructures nodes) never keep the template's "Node"/"Entry Node" texts: they are
    named after the asset of their `globalAssetId` (displayName and, if not given, description of that asset, en/de;
    `vf_common/aas/entities.py`, also for runtime workpiece builds). Nodes without an AAS of their own
    (CoManagedEntity, e.g. an ISA-95 area or a component batch) get an explicit `_displayName: {en, de}`.
  - `repo:<path>` embeds a file
  - `$include: common/<file>.yaml` merges a shared fragment; `$include: "common/<file>.yaml#A.B"` merges only the
    mapping at key path A.B (named fragments, e.g. `common/product_passport_pc3280.yaml`); keys next to it override
- **Quote** every text containing `,` or `:` inside flow mappings (`{en: "a, b"}`); the build rejects broken
  language maps.
- Documents: `aas/data/documents/<ID>.yaml` → `uv run aas/scripts/make_documents.py` → `aas/files/docs/<ID>.pdf`.
- Validate: `uv run -m provisioner check --only TAG1,TAG2` (prints MISSING mandatory values and UNKNOWN keys), then
  `uv run -m provisioner build`.
