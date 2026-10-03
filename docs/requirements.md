# Requirements

Status legend: ☐ open · ◐ in progress · ☑ done. "M" is the planned milestone (see [PLAN.md](PLAN.md#6-milestones)).
Verification: **T** automated test, **I** inspection/review, **D** demonstration (screenshot/video).

## 1. Goal

A 3D virtual factory for **training, education and research** in which simulated machines and products
have **Asset Administration Shells (AAS)** in a local **Eclipse BaSyx Go** environment, with data flows
that mirror a genuine manufacturing environment.

## 2. Functional requirements

### 2.1 Production process

| ID | Requirement | M | Verif. | Status |
|---|---|---|---|---|
| FR-01 | The factory produces a realistic product continuously: an ISO 15552 pneumatic cylinder with a red protective end cap. | M1 | D | ☑ |
| FR-02 | A "black box" assembly cell placed upstream of the conveyor outputs finished products at a configurable takt. Its internal process stays hidden; it exposes only its interface and its AAS. | M1 | T, D | ☑ |
| FR-03 | A belt conveyor transports the products. Its speed is configurable and it can be started and stopped by the PLC. | M1 | T, D | ☑ |
| FR-04 | Light barriers detect products: one at the infeed and one at the inspection position. | M1 | T | ☑ |
| FR-05 | A quality-assurance station with a colour sensor classifies each product: **red = OK** (cap present); any other colour = NOK (cap missing or wrong). | M1 | T | ☑ |
| FR-06 | A UR5e robot arm picks each inspected product and places it in **KLT A (good)** or **KLT B (reject)** according to the QA result. | M1 | T, D | ☑ |
| FR-07 | Full KLTs trigger an exchange request. The exchange is done by an operator (training mode) or automatically (demo/agent mode). *(M5: automatic exchange, manual exchange from the HMI or by clicking the KLT, BPMN task "Exchange KLT" in the Tasklist and on the MES terminal)* | M5 | D | ☑ |
| FR-08 | A virtual PLC controls the line using a PackML state model (Start/Stop/Hold/Reset/Abort/Clear …). | M1 | T | ☑ |
| FR-09 | Defect rates and fault scenarios can be configured: missing cap, wrong cap, sensor contamination, robot protective stop, conveyor fault. *(M5: fault inputs in CV01/QS01/LB01/LB02/AC01/RB01, PLC alarms 101–401, stack light SL01, 5 data-driven scenarios (`godot/config/scenarios`), writable via UNS/AID; [scenarios.md](interfaces/scenarios.md))* | M5 | T, D | ☑ |

### 2.2 Device models and extensibility

| ID | Requirement | M | Verif. | Status |
|---|---|---|---|---|
| FR-10 | Each device's behaviour is encapsulated in a dedicated component with an interface closely aligned to **FMI 3.0 Co-Simulation**, described by a valid FMI 3.0 `modelDescription.xml`. | M1 | T | ☑ |
| FR-11 | Devices are interchangeable: replacing a device model or view needs no changes to other devices, the PLC or the integration layer. | M1 | I, T | ☑ |
| FR-12 | The factory layout (device instances, positions, signal connections) is defined declaratively and can be reorganised without code changes. | M1 | D | ☑ |
| FR-13 | Each device has interfaces to the backend: telemetry, events and commands via MQTT (UNS topics). | M4 | T | ☑ |

### 2.3 AAS / BaSyx integration

| ID | Requirement | M | Verif. | Status |
|---|---|---|---|---|
| FR-20 | A local BaSyx Go environment (v1.1.0) runs via docker compose. | M0 | T | ☑ |
| FR-21 | AAS exist for: **product type**, **workpiece instances**, **robot**, **light barriers**, **conveyor**, plus the QA station, assembly cell, PLC, KLTs and the line. *(27 static AAS incl. stack light; workpiece instance AAS created per part by the MES since M4)* | M3/M4 | T | ☑ |
| FR-22 | Machine AAS contain at least a Digital Nameplate, technical data, **energy consumption** (static rating + live), **CO₂ footprint**, operational data and an interface description. *(live energy/CO₂e since M4; for Type/Instance pairs technical data and CO₂ footprint sit on the type AAS; M7: operational data limited to state and slow values, history via the TimeSeries LinkedSegment to the historian, ADR-0019)* | M3/M4 | T | ☑ |
| FR-23 | The product-type AAS contains a **recipe** and a **bill of materials**, plus nameplate, technical data and declared PCF. | M3 | T | ☑ |
| FR-24 | Each workpiece-instance AAS contains its **quality** results, its **CO₂ footprint** (actual) and its production log/genealogy. It is created when the product is created and updated along the process. | M4 | T | ☑ |
| FR-25 | IDTA submodel templates are used wherever one exists, with exact semantic IDs. Deviations are documented. | M3 | T, I | ☑ |
| FR-26 | Dynamic data (power, energy, states, counters) is synchronised from the shop floor to the AAS by an edge data bridge, not by the devices themselves. | M4 | T | ☑ |
| FR-27 | External clients (AI agents) can control the line through standard AAS Operations, delegated to a gateway. *(M7: the gateway resolves its endpoints from Control Component → AID; Control Component skills are executable via ExecuteSkill, ADR-0020)* | M4 | T | ☑ |
| FR-28 | Workpiece-instance AAS are ephemeral per factory session. Static AAS are preloaded on stack start. | M4 | T | ☑ |

### 2.4 Visualisation and interaction

| ID | Requirement | M | Verif. | Status |
|---|---|---|---|---|
| FR-30 | 3D models are created in Blender (via MCP) and are recognisable but low-poly. | M2 | D | ☑ |
| FR-31 | Models are animated: products move along the conveyor, robot joints rotate, rollers turn, indicator lights react. | M1/M2 | D | ☑ |
| FR-32 | An in-world AAS inspector shows the AAS of any asset, including live values. | M5 | D | ☑ |
| FR-33 | The UI is available in German and English. | M5 | I | ☑ |
| FR-34 | A demo mode runs autonomously with a camera tour. A headless/fast-forward mode supports agents. *(M5: demo tour (F1/--vf-tour), simulation speed 1×/2×/4×, headless line runs)* | M5 | D | ☑ |

## 3. Non-functional requirements

| ID | Requirement | M | Verif. | Status |
|---|---|---|---|---|
| NFR-01 | **Performance:** 60 FPS at 1080p on an Intel Iris Xe-class iGPU. Budget ≤ 250 k primitives and ≤ 450 draw calls, both including the shadow pass, with full KLTs (ADR-0010). *(M6: draw calls 449/450 and primitives 66 k/250 k with full KLTs and the training UI; Low/Medium/High presets; not measured on an Iris Xe device (decision M6 review))* | M2/M6 | T (perf scene), D | ☑ |
| NFR-02 | **XR-readiness:** VR can be added later without restructuring (1 unit = 1 m, PlayerRig abstraction, world-space UI, XR-capable renderer). The desktop PC is fully supported. *(M6: XRRig (OpenXR) behind the PlayerRig interface, world-space UI, review in architecture/xr-readiness.md)* | M0–M6 | I | ☑ |
| NFR-03 | **Modularity:** semantically related aspects are grouped into modules, with high cohesion and low coupling. *(arch_check: 314/314 dependency edges conformant)* | all | I, T | ☑ |
| NFR-04 | **Architecture adherence ≥ 95 %**, measured by `tools/arch_check.py`. Exceptions are documented. *(100 % adherence, 0 exceptions)* | all | T | ☑ |
| NFR-05 | **Complexity limits:** ≤ 300 lines per file, ≤ 40 lines per function, ≤ 110 characters per line. Exceptions are justified inline. *(complexity_check covers GDScript and Python: 0 problems)* | all | T | ☑ |
| NFR-06 | **Documentation:** requirements, architecture (arc42) including interfaces and data types, implementation concepts, ADRs and open issues are maintained in `docs/`. *(arc42 + 18 ADRs + interfaces + runtime views + conformance and final report)* | all | I | ☑ |
| NFR-07 | **Realism:** data flows follow the OT/IT layering of real plants (field devices ↔ PLC ↔ edge ↔ MES/AAS). Device parameters (dimensions, speeds, power) are plausible. *(FMU devices ↔ virtual PLC ↔ UNS gateway ↔ bridge/MES ↔ AAS/BPMN, see runtime-ot-it.md)* | all | I | ☑ |
| NFR-08 | **Reproducibility:** pinned container images and dependencies. 3D assets are generated by versioned scripts. *(images pinned (BaSyx 1.1.0, aas-gui digest, Operaton 2.1.5, Node-RED 4.1.15-22), uv.lock, Blender build scripts)* | all | I | ☑ |
| NFR-09 | **Standards:** AAS metamodel/API V3.x, IDTA templates, FMI 3.0, ISA-95 hierarchy, PackML, ISO 22400 KPIs and ISO 14067 PCF terminology where applicable. *(see docs/conformance-report.md)* | all | I | ☑ |
| NFR-10 | **Robustness:** the simulation keeps running when the MQTT broker or BaSyx is unavailable. The bridge stores and forwards. *(M4: simulation and services survive broker/BaSyx outages and reconnect; retained telemetry restores state, the bridge does not buffer (latest value wins))* | M4 | T | ◐ |
