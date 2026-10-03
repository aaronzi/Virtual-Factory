# Virtual Factory

A 3D virtual factory for **training, education and AI-agent research** with **Asset Administration Shell (AAS)**
digital twins in **Eclipse BaSyx Go**.

A continuous line takes ISO 15552 pneumatic cylinders from a black-box assembly cell, transports them on a belt
conveyor, inspects the red protective end cap with a colour sensor, and sorts them with a UR5e robot into good and
reject containers. Every machine, the product type and every workpiece have an AAS built from IDTA submodel
templates. Data flows like in a real plant: FMI-style device models and a virtual PLC (Godot) → MQTT unified
namespace → AAS-driven bridge and MES (BPMN workflows) → BaSyx Go; IT systems and agents command the line through
AAS operations.

**Status:** all milestones (M0–M6) complete - see the [final report](docs/final-report.md).

![Training UI: AAS inspector in the factory](docs/screenshots/m5-inspector-rb01.png)

## Quick start
```bash
docker compose -f infra/docker-compose.yml up -d     # BaSyx Go, AAS Web UI, MQTT, Operaton, bridge, MES, ops gateway
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```
Or run a desktop build (`tools/export_builds.sh` → `build/VirtualFactory-{macos,windows,linux}.zip`).

| What | Where |
|---|---|
| Factory (click devices/parts for their AAS, Esc menu) | Godot app |
| AAS Web UI / AAS API | http://localhost:3001 · http://localhost:8091 |
| Digital product passports (BaSyx DPP API) | http://localhost:8093/swagger |
| BPMN Cockpit / Tasklist (demo/demo) | http://localhost:8092/operaton/app/ |
| MQTT (UNS) | localhost:1883, ws://localhost:9001 |
| Live dashboard *LINE01 live* (Grafana; read-only, log in as admin/editor to edit) | http://localhost:3002 |
| Node-RED sandbox (optional, `--profile sandbox`) | http://localhost:1880 |

## Documentation
- [User guide](docs/user-guide.md) · [scenario walkthrough](docs/training/scenario-walkthrough.md)
- [Requirements](docs/requirements.md) · [architecture (arc42)](docs/architecture/README.md) · [ADRs](docs/adr/README.md)
- Interfaces: [FMI](docs/interfaces/fmi-interface.md) · [UNS](docs/interfaces/uns.md) ·
  [AAS model](docs/interfaces/aas-model.md) · [services](docs/interfaces/services.md) · [scenarios](docs/interfaces/scenarios.md)
- [Conformance report](docs/conformance-report.md) · [open issues](docs/open-issues.md) · [plan](docs/PLAN.md)
- [Development and CI](docs/development.md): checks, CI workflows, integration suite (`tools/ci_integration.sh`)

## Repository layout
| Path | Content |
|---|---|
| `godot/` | Godot 4.7 project: device models (FMI-3-aligned), virtual PLC, UNS gateway, training UI, 3D world |
| `services/` | Python services (uv workspace): provisioner, AIMC bridge, MES, ops gateway, shared library |
| `aas/` | IDTA and custom templates, asset data, documents |
| `bpmn/` | BPMN models (workpiece lifecycle, production order) |
| `blender/` | Blender sources and generator scripts for all 3D assets |
| `infra/` | docker compose stack (BaSyx Go, Mosquitto, Operaton, services, Node-RED) |
| `tools/` | Architecture/complexity checks, test runners, exports, screenshots |
| `docs/` | Requirements, architecture, ADRs, interfaces, reports, user guide |
