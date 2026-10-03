# Virtual Factory

A 3D virtual factory for **training, education and AI-agent research** with **Asset Administration Shell (AAS)**
digital twins in **Eclipse BaSyx Go**.

A continuous line takes ISO 15552 pneumatic cylinders from a black-box assembly cell, transports them on a belt
conveyor, inspects the red protective end cap with a colour sensor, and sorts them with a UR5e robot into
good and reject containers. Every machine, the product type and every workpiece have an AAS. Data flows like it
does in a real plant: device models and a virtual PLC (Godot) → MQTT unified namespace → edge/MES services → BaSyx Go.

**Status:** M2 (3D assets from Blender, roofed hall, Compatibility renderer) complete. See [docs/PLAN.md](docs/PLAN.md) for the plan and milestones.

![Line](docs/screenshots/m2-line.png)

![Blender animation from a recorded simulation run](docs/screenshots/m2-blender-animation.gif)

## Quick start
```bash
docker compose -f infra/docker-compose.yml up -d     # BaSyx Go + AAS Web UI + MQTT
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```
AAS Web UI: http://localhost:3001 · AAS API: http://localhost:8091 · MQTT: localhost:1883 / ws://localhost:9001

## Repository layout
| Path | Content |
|---|---|
| `godot/` | Godot 4.7 project: device models (FMI-3-aligned), virtual PLC, 3D world, UI |
| `services/` | Python edge/IT services (uv workspace) |
| `aas/` | AAS master data and generated AASX |
| `blender/` | Blender sources and generator scripts for all 3D assets |
| `infra/` | docker compose stack |
| `tools/` | Architecture/complexity checks, test runners, screenshot helper |
| `docs/` | Requirements, arc42 architecture, ADRs, interfaces, open issues, user guide |
