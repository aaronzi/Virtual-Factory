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
- Digital product passports (BaSyx Go DPP API): http://localhost:8093 (Swagger UI at `/swagger`) - the item-level
  passport of every produced part and the model passport of the product type, see *Product passports* below
- MQTT: `localhost:1883` (TCP), `ws://localhost:9001` (WebSocket); BaSyx change events on `vf/basyx/#`
- BPMN engine (Operaton): Cockpit http://localhost:8092/operaton/app/cockpit/, Tasklist
  http://localhost:8092/operaton/app/tasklist/ (local user `demo` / `demo`), REST `/engine-rest`
- Historian (InfluxDB 3 Core): http://localhost:8181, database `vf`, no token - every UNS value of the session,
  one table per device (`cv01`, `rb01`, …); see *Query the history* below
- Dashboards (Grafana): http://localhost:3002 - live dashboard *LINE01 live*, read-only without login;
  log in as `admin` or `editor` (password `virtualfactory`) to edit, see *Dashboards (Grafana)* below
- Services: `bridge` (UNS → AAS), `historian` (UNS → InfluxDB), `mes` (workpiece AAS, BPMN workers),
  `ops-gateway` (AAS operations → PLC),
  see [interfaces/services.md](interfaces/services.md). Logs: `docker compose -f infra/docker-compose.yml logs -f mes`

Stop it with `docker compose -f infra/docker-compose.yml down`. The databases (AAS, InfluxDB) and the BPMN engine
are ephemeral.
After changing code in `services/`, rebuild with `docker compose -f infra/docker-compose.yml up -d --build`.

## Desktop builds
```bash
tools/export_builds.sh            # all three, or: tools/export_builds.sh macOS
```
Produces `build/VirtualFactory-macos.zip` (universal .app, ad-hoc signed - on first start use right-click → Open),
`build/VirtualFactory-windows.zip` (x86_64 .exe) and `build/VirtualFactory-linux.zip` (x86_64). The builds contain
the complete simulation and training UI; the backend (`docker compose`) is optional and is found on localhost.
Developer options are passed after `--`, e.g. `VirtualFactory.exe -- --vf-lang=de --vf-quality=0`. Requires the
Godot 4.7.2 export templates (Editor → Manage Export Templates).

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
| Left click | Press buttons on panels; click a device, a workpiece or the control cabinet to open its AAS |
| Esc / F1 | Open/close the menu (language, quality, speed, scenarios, demo tour, data flow) |

## What you see
The line runs automatically (PackML auto-start). The overlay shows the line state, the inspection results, KLT fill
levels, robot step and line power. Full KLTs are exchanged automatically 4 s after the last part was placed
(`auto_exchange`; can be switched off and KLTs exchanged manually with the MQTT command `klt_exchange_command`).

## Factory and AAS together (M4)
With the backend and the factory running:
- Live state values appear in the AAS of every device (OperationalData: states, counters, per-part measurements;
  EnergyConsumption). High-rate signals (robot joints, belt position, …) are only in the historian; the device's
  TimeSeries submodel tells which variables are recorded and how to query them (LinkedSegment `Historian`).
- Each released cylinder gets its own AAS (`PC3280_2026_<number>`), filled at inspection and packing: executed
  processes, quality inspection, measurement values, actual carbon footprint, location in the KLT. The KLT AAS list
  their contents (HierarchicalStructures). A new factory start begins a new session and removes the old instances.
- Cockpit shows one `Workpiece lifecycle` instance per part in production.
- **Production order:** in Tasklist *Start process → Production order (MES)* (quantity, manual KLT exchange,
  reject rate limit). With manual exchange, full KLTs appear as task *Exchange KLT*; completing it exchanges the KLT.
- **Command the line through its AAS:** LINE01 → LineControl → `ExecutePackMLCommand` (Start, Stop, Hold, Unhold,
  Reset, Suspend, Unsuspend, Abort, Clear), `ExchangeContainer`, `SetAutoExchange` - e.g. with curl, see
  [interfaces/services.md](interfaces/services.md#starting-a-production-order).

## Query the history (historian)
Every UNS value of the running session is stored in InfluxDB 3 (http://localhost:8181, database `vf`, no token):
one table per device, one column per FMI output, column `time` (UTC, simulation time base) and tag `session`.
The SQL statement for a device is in its AAS: TimeSeries → Segments → Historian → `Query`, sent to `Endpoint`:

```bash
curl -s -G 'http://localhost:8181/api/v3/query_sql?db=vf&format=json' \
  --data-urlencode "q=SELECT time, q1, q2, power FROM rb01 WHERE time >= now() - INTERVAL '1 minute' ORDER BY time"
curl -s -G 'http://localhost:8181/api/v3/query_sql?db=vf&format=json' \
  --data-urlencode "q=SELECT date_bin(INTERVAL '10 seconds', time) AS t, (max(energy) - min(energy)) * 360000 AS w
  FROM ac01 GROUP BY 1 ORDER BY 1"   # mean power per 10 s from the energy counter
```

Rows are sparse: a column only has a value in the rows where it changed (power, for example, only when the
state changes - use the `energy` counter or the step function for averages). The workpiece carbon footprint uses the
same data (energy of the part's time on the line, see [interfaces/aas-model.md](interfaces/aas-model.md) §6a).

## Dashboards (Grafana)
Grafana at http://localhost:3002 opens the dashboard **LINE01 live** (folder *Virtual Factory*) with the values of
the running process from the historian: refreshed every 5 s, last 15 minutes by default. The selector *Session*
shows `latest` (follows the newest Godot start) or an older session. Links at the top open the AAS Web UI and
Operaton Cockpit/Tasklist.

![LINE01 live](screenshots/m8-grafana.png)

| Panel | Historian data (table.column) |
|---|---|
| State, PackML state (timeline) | `plc01.packml_state` (ISA-TR88 state names) |
| Parts, Reject rate, Parts per minute, Reject rate (cumulative), Throughput | `plc01.parts_total`, `parts_ok`, `parts_nok` (throughput = inspected parts per hour in the time range) |
| OEE (availability, performance, quality) | PackML state durations of the session (`plc01.packml_state`), counters; ideal cycle = AC01 takt 12 s - same formula as the HMI |
| Alarms | `plc01.alarm_code` (100 E-stop, 101 CV01 drive, 201/202 RB01, 301/302 light barrier stuck, 401 infeed timeout) |
| Stack light SL01 | `sl01.red_on`, `amber_on`, `green_on`, `buzzer_on` |
| Line power, Power per device (stacked), Energy per device, Line energy | `power` (latest) and the `energy` counters (kWh) of AC01, RB01, CV01, QS01, LB01, LB02, SL01; mean power per 10 s from the counter |
| Compressed air, Compressed air flow AC01 | `ac01.air_consumption` (Nl) → Nl/min |
| QS01 colour distance ΔE*ab per part | `qs01.delta_e`, limit 25 (red area) |
| AC01 leak rate / stroke time per part | `ac01.last_leak_rate` (limit 1.0 cm³/min), `ac01.last_stroke_time` (0.28 … 0.36 s) |
| Robot cycles, RB01 cycle time | `rb01.cycle_count` (time between two increments), KLT `exchange_count` |
| KLT fill levels, KLT fill now | `klta01.fill_count`, `kltb01.fill_count` (capacity 12) |

**Access:** without login everyone is a *Viewer* (read-only). *Sign in* (top right) with `admin` / `virtualfactory`
or `editor` / `virtualfactory` (local defaults, change them before exposing port 3002) to edit: panel menu →
*Edit*, then *Save dashboard*. Saved changes stay in the Docker volume `vf_grafana-data` (also across `down`) until
the dashboard file `infra/grafana/dashboards/line01-live.json` in the repository changes; to keep a change for
everyone, export the JSON (*Export* → *Export as JSON*) into that file. New dashboards can be saved as well.
Reset Grafana to the repository state:
`docker compose -f infra/docker-compose.yml rm -sf grafana && docker volume rm vf_grafana-data`.

At simulation speed 2×/4× the UNS timestamps run ahead of the clock; use a time range that ends in the future
(e.g. `now-15m` to `now+15m`) or switch back to 1× (O43).

## Product passports (DPP API)
Every cylinder gets an item-level digital product passport while it is produced (its workpiece AAS, ADR-0021): as-built
technical data (leak rate, stroke times, cap colour), the component batches it was built from (reported by the
assembly cell; each feeder changes its batch after its own number of parts), material composition and recycled
content per batch, carbon footprint, contacts incl. take-back, and - for packed good parts - an *inspection
certificate 3.1* PDF plus the data sheet, manuals and the REACH SVHC information. Rejects get the documents but no
certificate; their passport is `Inactive`.

Open it from the inspector (*Open passport (DPP API)*) or with the BaSyx DPP API:
```bash
enc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
curl -s "http://localhost:8093/v1/dppsByProductId/$(enc https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000005)" | jq .
```
More examples (by DPP id, single element, find all parts with a given batch):
[interfaces/services.md](interfaces/services.md#dpp-api). Passports are deleted with the session like all
workpiece AAS (O41).

## Training UI (M5)
Everything an operator needs is in the 3D scene (world-space panels, ready for VR later):
- **AAS inspector:** click any device (or the control cabinet for PLC01, or a cylinder on the belt or in a KLT)
  to open its AAS in front of you: thumbnail, submodels, element tree. The visible submodel updates live when
  BaSyx reports a change (MQTT event → fetch). *Open type AAS* jumps from an instance to its type. For a KLT the
  inspector offers the exchange (completes a pending *Exchange KLT* task, otherwise exchanges directly); for a
  cylinder *Open passport (DPP API)* opens its digital product passport in the browser.
- **HMI** (stand left of the conveyor): PackML state, Reset/Start/Stop/Hold/Unhold/Suspend/Unsuspend/Abort/Clear
  (only allowed commands are enabled), parts, reject rate, OEE (availability × performance × quality), automatic
  KLT exchange on/off and manual exchange. The HMI talks to the PLC directly (fieldbus), like a real panel.
- **MES terminal** (right of the robot cell): the open BPMN user tasks (same as Operaton Tasklist) with their form
  fields; *Complete task* finishes them.
- **Stack light** on the control cabinet: green = EXECUTE, amber = held/suspended/acting, red = stopped/aborted/fault.
- **Safety fence door** (right side of the robot cell): click to open - the robot stops (protective stop), the line
  holds with alarm 201; click again to close and the line resumes.
- **Emergency stop** (red button on the HMI stand): click to press - it latches, the safety circuit stops the robot
  and the line aborts with alarm 100. Click again to release (like twisting a real E-stop), then *Clear* and
  *Reset* on the HMI. While it is latched nothing (door, scenario, MQTT command) can release the robot.
- **Menu (Esc or F1):** language English/Deutsch, render quality Low/Medium/High, simulation speed 1×/2×/4×, training
  scenarios (start/stop), demo tour (camera flies through the line with captions and opens AAS), data-flow view
  (IT layer above the line; packets follow real UNS events and BaSyx change events; violet packets = telemetry
  stored by the historian), *Open dashboard (Grafana)* (opens *LINE01 live* in the browser; URL
  `grafana_url` in `godot/config/backend.json`, `--vf-grafana-url=…`).

Developer options (after `--`): `--vf-lang=de`, `--vf-quality=0|1|2`, `--vf-tour`, `--vf-dataflow`,
`--vf-inspect=<AAS tag>`, `--vf-estop=1` (press the E-stop), `--vf-scenario=<id>`, `--vf-ui=off`, `--vf-xr` (OpenXR headset, see
[xr-readiness](architecture/xr-readiness.md)), `--vf-aas-url=…`, `--vf-bpmn-url=…`,
`--vf-aas-events=<broker url|off>`. Endpoints: `godot/config/backend.json`.

## Node-RED sandbox (optional)
A Node-RED instance for learners to experiment with the UNS and the AAS API. It is not part of the core data
path (nothing in the stack depends on it) and only starts with the compose profile `sandbox`:
```bash
docker compose -f infra/docker-compose.yml --profile sandbox up -d nodered   # add to a running stack
docker compose -f infra/docker-compose.yml --profile sandbox up -d           # or everything incl. Node-RED
```
- Editor: http://localhost:1880 (image `nodered/node-red:4.1.15-22`). **No authentication** - local use only.
- Inside compose the broker is `mqtt:1883` and the AAS API `http://aas-env:8091` (from the host: `localhost`).
- Only core nodes are used, so the examples work offline once the image is pulled.

Example flows (one tab each, every node is commented; double-click a node or see the tab's info panel):

| Tab | What it shows |
|---|---|
| 1 UNS explorer | Subscribes `vf/plant01/final-assembly/line01/+/event/#`, counts events per type, detects `seq` gaps |
| 2 Reject alarm | `part_inspected` with `result` = 2 → sliding-window counter → alert on `…/line01/sandbox/alert` when more than `LIMIT` rejects lie within `WINDOW_S` s (a test inject simulates rejects without the factory) |
| 3 Read the AAS | `GET /submodels/{base64url id}/$value` of PLC01 OperationalData → part counters (id encoded in the flow) |
| 4 Call an AAS operation | Invokes LINE01 LineControl `ExecutePackMLCommand` with Hold / Unhold (really commands the line) |

Storage: the example flows come read-only from `infra/nodered/flows.json` (settings:
`infra/nodered/settings.js`) and are copied **once** into the named volume `vf_nodered-data`; your edits
(Deploy) persist there across restarts and `down`/`up`. To go back to the repository examples (this discards
your flows - export them first with *Menu → Export*):
```bash
docker compose -f infra/docker-compose.yml rm -sf nodered && docker volume rm vf_nodered-data
```
`down` without the profile leaves Node-RED (and the network) running; stop everything with
`docker compose -f infra/docker-compose.yml --profile sandbox down`. Alerts published by the sandbox on
`…/sandbox/#` are not consumed by any service.

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
