# Open issues and risks

| ID | Type | Description | Mitigation / next step | Status |
|---|---|---|---|---|
| R1 | Risk | BaSyx Go MQTT eventing is experimental and works at submodel granularity | Godot polls at 1 Hz; eventing is an optional switch later | open |
| R2 | Risk | basyx-python-sdk 2.2 vs BaSyx Go metamodel V3.2 | **Basic round-trip verified in M0** (`tools/tests/test_basyx_smoke.py`). Full template check in M3 | mitigated (basic) |
| R3 | Gap | No IDTA templates for energy consumption, quality inspection, recipe or production log | Custom submodels with their own semantic IDs and CDs, documented as deviations | open |
| R4 | Risk | Physics instability of workpieces on the belt | **M1: stable in a 600 s run** (no tipping; stop accuracy ±10 mm). `can_sleep=false` needed ([ADR-0009](adr/0009-physical-transport-and-items.md)) | mitigated |
| R5 | Risk | REST write load from telemetry and workpieces | Throttling and deadband in the bridge, ephemeral sessions | open |
| R6 | Constraint | Godot MCP has no screenshot or script-editing tools | Direct file authoring, `tools/screenshot.sh` | mitigated |
| R7 | Risk | UR5e IK singularities / wrist flips | Analytic IK verified on 2000 random poses; elbow-up home, closest-solution continuity. Residual ≤ 0.2 mm near wrist singularity (single-precision `Transform3D`) | mitigated |
| R8 | Legal | UR5e appearance resembles the real product | No logos; name used only on the nameplate | open |
| R9 | Simplification | PCF allocation is simplified | Method documented, factors configurable | open |
| R10 | Constraint | VR not testable on macOS | Deferred (ADR-0003) | accepted |
| O1 | Issue | aas-gui publishes no version tags | Pinned by digest | open |
| O2 | Issue | Godot export templates not installed | Install in M6 for builds | open |
| O3 | Limitation | Robot FMU state snapshot excludes a running job | Take snapshots between jobs; extend if scenario snapshots need it | open |
| O4 | Issue | Compatibility renderer looks brighter than Mobile | Resolved: Compatibility is now the default; lighting tuned and sRGB→linear palette fix ([ADR-0010](adr/0010-compatibility-renderer-indoor-lighting.md)) | closed |
| O5 | Issue | GUT skipped scripts with parse errors silently | Fixed: `tests/compile_all.gd` + error grep in `tools/run_godot_tests.sh` | closed |
| O6 | Limitation | Part tracking FIFO assumes no parts are lost between LB01 and LB02 | Infeed timeout counts faults; add a belt-end light barrier / reconciliation if scenarios remove parts | open |
| O7 | Improvement | Lighting is unbaked (directional key + fill + ambient) | Optional LightmapGI bake for the static hall (needs an editor bake step) | open |
| O8 | Issue | Godot extracts embedded glTF decal textures next to each .glb (duplicate PNGs) | Acceptable (small, LFS). Could switch the import setting to keep textures embedded | open |
| O9 | Limitation | NFR-01 not yet verified on a real Iris Xe-class iGPU (FPS on the dev machine is display-capped) | Measure on target hardware in M6; draw-call/primitive budgets are hardware-independent | open |
| O10 | Limitation | Safety fence and door are static props; the door switch is not wired yet | M5 training scenario: fence door as a device (protective stop) | open |
