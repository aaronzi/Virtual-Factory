# User guide

## Prerequisites
Godot 4.7, Docker (Compose v2+), uv (Python 3.12), Git LFS. Optional: Blender 5.2 for editing assets and
MQTT Explorer for watching UNS topics.

## Start the backend
```bash
docker compose -f infra/docker-compose.yml up -d
```
- AAS Web UI: http://localhost:3001
- AAS API (BaSyx Go AAS Environment): http://localhost:8091 (Swagger UI at `/swagger`)
- MQTT: `localhost:1883` (TCP), `ws://localhost:9001` (WebSocket)

Stop it with `docker compose -f infra/docker-compose.yml down`. The database is ephemeral (tmpfs).

## Start the factory
Open `godot/project.godot` in Godot 4.7 and press Play, or run:
```bash
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

### Desktop controls
| Input | Action |
|---|---|
| Right mouse button (hold) + mouse | Look around |
| W A S D | Move |
| Q / E | Down / up |
| Shift | Move faster |
| Left click | Point / interact |

## What you see
The line runs automatically (PackML auto-start). The overlay shows the line state, the inspection results, KLT fill
levels, robot step and line power. Full KLTs are exchanged automatically after 4 s.

## AAS model (provisioner)
`docker compose up` runs the one-shot `provisioner` service, which generates one AASX per asset into
`infra/basyx/preload` before BaSyx Go starts. Locally:
```bash
uv run -m provisioner check                  # build + validate, report MISSING/UNKNOWN values
uv run -m provisioner build                  # write infra/basyx/preload/*.aasx (+ aas/build/environment.json)
uv run -m provisioner upload                 # replace the AAS in a running BaSyx (no restart)
uv run tools/check_aasx.py                   # IDTA aas-test-engines on all packages
uv run tools/aas_template_tree.py Nameplate-3.0 3   # inspect a template
uv run tools/fetch_idta_templates.py         # re-vendor IDTA templates and concept descriptions
```
See [interfaces/aas-model.md](interfaces/aas-model.md) for the model and the data format.

## Rebuilding 3D assets
Blender 5.2 with the MCP add-on (or the Blender Python console):
```python
exec(open("<repo>/blender/scripts/build_all.py").read())
```
Decal images: `uv run blender/scripts/make_decals.py`. Afterwards run a Godot import
(`godot --headless --import` in `godot/`). Demo animation: record with
`godot --headless --fixed-fps 60 -s res://tests/tools/record_demo_trajectory.gd`, then run
`blender/scripts/animate_demo.py` in Blender and open `blender/demo_animation.blend`.
See [architecture/asset-pipeline.md](architecture/asset-pipeline.md).

## Developer commands
| Command | Purpose |
|---|---|
| `tools/run_godot_tests.sh` | GDScript unit tests (GUT, headless) |
| `uv run pytest` | Python unit tests |
| `uv run pytest -m integration` | Integration tests against the running stack |
| `uv run tools/arch_check.py` | Architecture conformance (≥ 95 %) |
| `uv run tools/complexity_check.py` | Function length limits |
| `(cd godot && uv run gdlint .)` | GDScript lint |
| `tools/run_line_simulation.sh [seconds]` | Headless line run, faster than real time, checks production invariants |
| `uv run tools/gen_interface_docs.py` | Regenerate `docs/interfaces/device-catalog.md` from the FMI model descriptions |
| `tools/screenshot.sh out.png [delay] [scene] --vf-camera=x,y,z,tx,ty,tz` | Review screenshot (camera override optional) |
| `godot --path godot -- --vf-perf-report=5` | Performance sample (FPS, draw calls, triangles) |
| `godot --path godot --rendering-method forward_plus` | High-end renderer for comparison (default is Compatibility) |
