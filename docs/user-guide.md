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
- MQTT: `localhost:1883` (TCP), `ws://localhost:9001` (WebSocket); BaSyx change events on `vf/basyx/#`
- BPMN engine (Operaton): Cockpit http://localhost:8092/operaton/app/cockpit/, Tasklist
  http://localhost:8092/operaton/app/tasklist/ (local user `demo` / `demo`), REST `/engine-rest`
- Services: `bridge` (UNS → AAS), `mes` (workpiece AAS, BPMN workers), `ops-gateway` (AAS operations → PLC),
  see [interfaces/services.md](interfaces/services.md). Logs: `docker compose -f infra/docker-compose.yml logs -f mes`

Stop it with `docker compose -f infra/docker-compose.yml down`. The database and the BPMN engine are ephemeral.
After changing code in `services/`, rebuild with `docker compose -f infra/docker-compose.yml up -d --build`.

## Start the factory
Open `godot/project.godot` in Godot 4.7 and press Play, or run:
```bash
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```
The factory publishes its state to the MQTT broker (UNS, see [interfaces/uns.md](interfaces/uns.md)); without a
running broker it works normally and reconnects in the background. Options after `--`: `--vf-uns=mqtt://host:1883`
or `--vf-uns=ws://host:9001` selects another broker, `--vf-uns=off` disables MQTT.

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
levels, robot step and line power. Full KLTs are exchanged automatically 4 s after the last part was placed
(`auto_exchange`; can be switched off and KLTs exchanged manually with the MQTT command `klt_exchange_command`).

## Factory and AAS together (M4)
With the backend and the factory running:
- Live values appear in the AAS of every device (OperationalData, EnergyConsumption, PowerTimeSeries).
- Each released cylinder gets its own AAS (`PC3280_2026_<number>`), filled at inspection and packing: executed
  processes, quality inspection, measurement values, actual carbon footprint, location in the KLT. The KLT AAS list
  their contents (HierarchicalStructures). A new factory start begins a new session and removes the old instances.
- Cockpit shows one `Workpiece lifecycle` instance per part in production.
- **Production order:** in Tasklist *Start process → Production order (MES)* (quantity, manual KLT exchange,
  reject rate limit). With manual exchange, full KLTs appear as task *Exchange KLT*; completing it exchanges the KLT.
- **Command the line through its AAS:** LINE01 → LineControl → `ExecutePackMLCommand` (Start, Stop, Hold, Unhold,
  Reset, Suspend, Unsuspend, Abort, Clear), `ExchangeContainer`, `SetAutoExchange` - e.g. with curl, see
  [interfaces/services.md](interfaces/services.md#starting-a-production-order).

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
