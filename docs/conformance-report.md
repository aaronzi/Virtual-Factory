# Conformance report (M7, 2026-10-03)

All numbers are produced by the checks in CI (`.github/workflows/ci.yml`) or by the commands named below.

## 1. Architecture and code quality

| Check | Result | Command |
|---|---|---|
| Module dependency rules (ADR-0006) | **100 %** adherence, 323/323 edges conformant, 0 exceptions (target 95 %) | `uv run tools/arch_check.py` |
| Complexity (file ≤ 300 lines, function ≤ 40 lines, line ≤ 110 chars) | 0 problems in 141 GDScript and 81 Python files | `uv run tools/complexity_check.py` |
| GDScript lint | clean | `(cd godot && uv run gdlint .)` |
| GDScript unit tests (GUT) | 104 passing, every script compiles | `tools/run_godot_tests.sh` |
| Python tests | 82 passing (+9 integration tests against the running stack) | `uv run pytest`, `uv run pytest -m integration` |
| Line integration run | 300 simulated seconds: throughput, OK/NOK accounting, KLT and robot invariants | `tools/run_line_simulation.sh 300` |
| Training scenarios | 5 scenarios (+ E-stop alarm 100 in the unit tests), expected PLC reaction (alarm, HELD/ABORTED, rejects) | `tools/run_scenarios.sh` |
| Device interface catalogue up to date | generated from the FMI model descriptions | `uv run tools/gen_interface_docs.py --check` |
| Rendering budget (ADR-0010) | 450 draw calls (≤ 450), 66 k primitives (≤ 250 k) with full KLTs and the training UI | `--vf-perf-report=5 --vf-perf-warmup=170` |

## 2. FMI 3.0

- 8 device/controller models (`modelDescription.xml`) validated against the FMI 3.0 XSD
  (`tools/tests/test_fmi_model_descriptions.py`).
- The GDScript API mirrors FMI 3.0 Co-Simulation (`Fmi3CoSimulation`: instantiate, initialization mode, doStep,
  get/set by value reference, state snapshot); deviations in [interfaces/fmi-interface.md](interfaces/fmi-interface.md).

## 3. Asset Administration Shell

| Item | Result |
|---|---|
| Metamodel | AAS V3.0 JSON, strictly deserialised with basyx-python-sdk 2.2 (`failsafe=False`) for every build |
| AASX packages | 27 packages, all pass the IDTA **aas-test-engines** file checks, concept descriptions included (`test_aasx_packages_are_conformant`) |
| Model size | 28 AAS (incl. the workpiece blueprint), 211 submodels, 1134 concept descriptions (+ workpiece instances at runtime) |
| IDTA templates | 30 vendored from the IDTA SMT repository with exact semantic ids: Nameplate 3.0, TechnicalData 2.0, ContactInformations 1.0, HandoverDocumentation 2.0, CarbonFootprint 1.0, CompanyData 1.0, HierarchicalStructures 1.1, CapabilityDescription 1.0, ControlComponentType/Instance 2.0, ProcessParameters 1.0, DppMetadata 1.0, ExecutedProcesses 1.0, MeasurementValue 1.0, AssetInterfacesDescription 1.1, AssetInterfacesMappingConfiguration 2.0, TimeSeries 1.1, SimulationModels 1.0, Reliability 1.0, FunctionalSafety 1.0, MaintenanceInstructions 1.0, SoftwareNameplate 1.0, ProcessVariablesForManufacturingKPICalculation 1.0, ProductionCalendar 1.0, DataRetentionPolicies 1.0, AssetLocation 1.0, Models3D 1.0, DBP MaterialComposition/Circularity 1.0 (reference) |
| Custom templates | 7 (EnergyConsumption, OperationalData, QualityInspection, ManufacturingRecipe 1.1, ProductMaterialComposition, ProductCircularity, LineControl 1.1) with IEC 61360 concept descriptions in en/de, documented deviations (ADR-0011) |
| Concept descriptions | Every Property/Range resolves to a concept description; measures carry their unit in the IEC 61360 data specification (not in text); numeric values have numeric data types (`test_concept_descriptions_carry_semantics_and_units`) |
| Interfaces | AID/AIMC generated from the FMI model descriptions; AID covers all FMI outputs, AIMC maps only discrete outputs + state/hours/energy (high-rate values go to the historian, ADR-0019); actions describe their acknowledgement (`ackForms`); AIMC transformations in Lua (`aimc_main`) as defined by the template |
| Control Component | Functional: the ops gateway resolves LineControl → Control Component endpoints → AID forms and is reconfigured by BaSyx change events; skills, modes and parameters from the AAS are enforced (ADR-0020) |
| Time series | IDTA TimeSeries 1.1 per device with UtcTime and record variables (FMI concept descriptions with units) and a LinkedSegment (Endpoint + SQL Query) into InfluxDB 3 Core (ADR-0019) |
| Server | BaSyx Go AAS Environment 1.1.0: 27/27 packages imported without failure; MQTT eventing (CloudEvents); operation invocation delegation |
| Known template quirks | Handled or documented, not patched in the vendored files (open issue O11) |

## 4. Standards used

| Standard | Where |
|---|---|
| IDTA AAS Part 1/2 (V3.0, API V3), IEC 61360 data specification | AAS model, REST access |
| IDTA submodel templates (see above), IDTA DPP 4.0 metadata | AAS model, product passport |
| FMI 3.0 Co-Simulation | Device and PLC models |
| ISA-95 (enterprise/site/area/line) | UNS topic hierarchy, HierarchicalStructures |
| ISA-TR88.00.02 (PackML) | PLC state machine, HMI, ops gateway |
| ISA-88 / IEC 61512 | Master recipe structure |
| IEC 61131-3 | PLC function blocks (TON, TOF, TP, R_TRIG, F_TRIG, CTU) |
| ISO 22400 | Line KPIs (OEE: availability, performance, quality) |
| ISO 14067 | Product carbon footprint: production-based allocation of measured energy per part (A1 components, A3 manufacturing incl. compressed air and production losses; R9) |
| VDI 2770 | Handover documentation classes |
| W3C WoT Thing Description | AID affordances (properties, actions, events) |
| CloudEvents 1.0 | BaSyx MQTT eventing |
| BPMN 2.0 | WorkpieceLifecycle, ProductionOrder |
| MQTT 3.1.1 | UNS (Godot client, services) |
| ISO 13850 / IEC 60204-1 (concept) | Latching emergency stop on the HMI stand, hard-wired with the fence door switch (simulation only, not a safety function) |
| CIE 1976 L\*a\*b\*, ΔE\*ab (CIE76) | Colour inspection |

## 5. Deviations

Deviations from the plan or the standards are recorded in the ADRs (0001–0020) and in
[open-issues.md](open-issues.md); none violates the module rules. Notable accepted simplifications: PCF loss
allocation per session (R9), generated black-box cell data (O23), BPMN task polling (O33), local default credentials (O34).
