# Open issues and risks

| ID | Type | Description | Mitigation / next step | Status |
|---|---|---|---|---|
| R1 | Risk | BaSyx Go MQTT eventing is experimental and works at submodel granularity | Godot polls at 1 Hz; eventing is an optional switch later | open |
| R2 | Risk | basyx-python-sdk 2.2 vs BaSyx Go metamodel V3.2 | **Basic round-trip verified in M0** (`tools/tests/test_basyx_smoke.py`). Full template check in M3 | mitigated (basic) |
| R3 | Gap | No IDTA templates for energy consumption, quality inspection, recipe or production log | Custom submodels with their own semantic IDs and CDs, documented as deviations | open |
| R4 | Risk | Physics instability of workpieces on the belt | Tuning; kinematic transport fallback | open |
| R5 | Risk | REST write load from telemetry and workpieces | Throttling and deadband in the bridge, ephemeral sessions | open |
| R6 | Constraint | Godot MCP has no screenshot or script-editing tools | Direct file authoring, `tools/screenshot.sh` | mitigated |
| R7 | Risk | UR5e IK singularities / wrist flips | Elbow-up selection, closest solution, workspace check | open |
| R8 | Legal | UR5e appearance resembles the real product | No logos; name used only on the nameplate | open |
| R9 | Simplification | PCF allocation is simplified | Method documented, factors configurable | open |
| R10 | Constraint | VR not testable on macOS | Deferred (ADR-0003) | accepted |
| O1 | Issue | aas-gui publishes no version tags | Pinned by digest | open |
| O2 | Issue | Godot export templates not installed | Install in M6 for builds | open |
