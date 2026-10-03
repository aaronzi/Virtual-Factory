# User guide

## Prerequisites
Godot 4.7, Docker (Compose v2+), uv (Python 3.12), Git LFS. Optional: Blender 5.2 for editing assets,
MQTT Explorer for watching UNS topics and an OPC UA client (UaExpert, or the asyncua CLI) for the PLC.

## Start the backend
```bash
docker compose -f infra/docker-compose.yml up -d
```
- AAS Web UI: http://localhost:3001
- AAS API (BaSyx Go AAS Environment): http://localhost:8091 (Swagger UI at `/swagger`)
- Digital product passports (BaSyx Go DPP API): http://localhost:8093 (Swagger UI at `/swagger`) - the item-level
  passport of every produced part and the model passport of the product type, see *Product passports* below
- GS1 Digital Link resolver: http://localhost:8096/01/04099999032808/21/<serial> - what the QR code on a part
  resolves to (passport page, links to DPP, AAS and certificate), see *Product passports* below
- MQTT: `localhost:1883` (TCP), `ws://localhost:9001` (WebSocket); BaSyx change events on `vf/basyx/#`
- BPMN engine (Operaton): Cockpit http://localhost:8092/operaton/app/cockpit/, Tasklist
  http://localhost:8092/operaton/app/tasklist/ (local user `demo` / `demo`), REST `/engine-rest`
- Historian (InfluxDB 3 Core): http://localhost:8181, database `vf`, no token - every UNS value of the session,
  one table per device (`cv01`, `rb01`, …); see *Query the history* below
- Dashboards (Grafana): http://localhost:3002 - live dashboard *LINE01 live*, read-only without login;
  log in as `admin` or `editor` (password `virtualfactory`) to edit, see *Dashboards (Grafana)* below
- PLC01 OPC UA server: `opc.tcp://localhost:4840/vf/plc01` (security None, anonymous), see *Browse the PLC
  (OPC UA)* below; the factory's PLC CPU connects to it on `localhost:4841`
- ERP simulator: http://localhost:8098 (status page, orders and batches), see *Orders (ERP simulator)* below
- Supplier side (ADR-0028): supplier AAS environment http://localhost:8191 (a second, separately operated BaSyx
  environment with the four suppliers, their product types and the AAS of every delivered batch) and the supplier
  portal http://localhost:8190/api/despatch-advices; see *Suppliers and batches* below
- Alarms & events: http://localhost:8099/api/alarms (ISA-18.2 alarms, acknowledge, journal), dashboard *Alarms &
  events* in Grafana, see *Alarms and events* below; sustainability KPIs: http://localhost:8097/api/kpis
- Services: `bridge` (UNS → AAS), `historian` (UNS → InfluxDB), `mes` (orders, workpiece AAS, BPMN workers),
  `sustainability` (carbon footprints), `erp` (order simulator), `alarms` (+ TimescaleDB `alarms-db`),
  `ops-gateway` (AAS operations → PLC over OPC UA), `plc-comm` (PLC01 OPC UA server), `edge` (OPC UA → UNS),
  `supplier` (supplier portal) with `supplier-aas-env` (+ `supplier-db`, `supplier-config`, `supplier-provisioner`),
  see [interfaces/services.md](interfaces/services.md). Logs: `docker compose -f infra/docker-compose.yml logs -f mes`

Stop it with `docker compose -f infra/docker-compose.yml down`. The databases (AAS, InfluxDB, alarms), the BPMN
engine and the ERP are ephemeral.
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
or `--vf-uns=ws://host:9001` selects another broker, `--vf-uns=off` disables MQTT. The PLC (PLC01) is not
published by Godot itself: its CPU feeds the OPC UA server `plc-comm` (port 4841), and the edge connector puts its
data on the UNS, like in a real plant. `--vf-backplane=off` publishes PLC01 directly over MQTT again (LineControl
operations then fail, the AAS points to OPC UA), `--vf-backplane=tcp://host:4841` selects another module.

### Desktop controls
| Input | Action |
|---|---|
| Right mouse button (hold) + mouse | Look around |
| W A S D | Move |
| Q / E | Down / up |
| Shift | Move faster |
| Left click | Press buttons on panels; click a device, a workpiece or the control cabinet to open its AAS |
| Mouse wheel / trackpad | Scroll the panel under the pointer (AAS inspector, MES terminal) |
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

## Browse the PLC (OPC UA)
With the backend and the factory running, PLC01 is an OPC UA server like a real controller
(`opc.tcp://localhost:4840/vf/plc01`, security policy None, anonymous):
- **UaExpert:** *Add server* → *Advanced* → endpoint URL `opc.tcp://localhost:4840/vf/plc01`, security None,
  anonymous. Below *Objects/PLC01*: `Status` (StateCurrent = PackML state, UnitModeCurrent), `Admin` (counters,
  alarm), `BaseStateMachine` (CurrentState, methods Reset … Clear - right-click → *Call*), `SetUnitMode`, `Program`
  (all PLC tags: I/O image, outputs, parameters), `Commands`, `Diagnostics` (CpuConnected). Drag variables into the
  data access view to watch them; *Event View* on `PLC01` shows the PartInspected/PartSorted events.
- **asyncua CLI** (installed with the Python workspace):
  ```bash
  uv run uals -u opc.tcp://localhost:4840/vf/plc01 -n "ns=2;s=PLC01" -l 2            # browse
  uv run uaread -u opc.tcp://localhost:4840/vf/plc01 -n "ns=2;s=PLC01.Status.StateCurrent"
  uv run uasubscribe -u opc.tcp://localhost:4840/vf/plc01 -n "ns=2;s=PLC01.Admin.ProdProcessedCount"
  uv run uacall -u opc.tcp://localhost:4840/vf/plc01 -n "ns=2;s=PLC01.BaseStateMachine" -m 2:Hold  # then 2:Unhold
  ```
- The AAS describes the server: PLC01 → AssetInterfacesDescription → `InterfaceOPCUA` (endpoint, node ids, browse
  paths, methods, event types). Without the factory running all values show *BadNoCommunication* and
  `Diagnostics.CpuConnected` is false.
- *Training UI → Menu → Data flow* shows PLC01's packets on the plant route PLC → OPC UA server → edge → broker
  and the ops gateway's method calls (yellow) going to the OPC UA server
  ([screenshot](screenshots/m9-dataflow-opcua.png)); the F1 menu shows `PLC OPC UA online/offline`.

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

The dashboard **Maintenance** (http://localhost:3002/d/vf-maintenance) shows the gripper finger wear and its
prognosis: see [Predictive maintenance](#predictive-maintenance).

| Panel (Maintenance) | Data |
|---|---|
| Health index, RUL (lower bound, h), RUL in grips, Health state, Maintenance order | `maintenance` table (component GR01) |
| Finger wear (limit 1.0 mm, slip from 0.85 mm), Grip force and closing time, Regrips | `rb01.finger_wear`, `grip_force`, `grip_close_time`, `grasp_retries`, `grip_cycles` |
| Maintenance alarms | alarm journal (alarms database) for 901 and 202 |

**Access:** without login everyone is a *Viewer* (read-only). *Sign in* (top right) with `admin` / `virtualfactory`
or `editor` / `virtualfactory` (local defaults, change them before exposing port 3002) to edit: panel menu →
*Edit*, then *Save dashboard*. Saved changes stay in the Docker volume `vf_grafana-data` (also across `down`) until
the dashboard file `infra/grafana/dashboards/line01-live.json` in the repository changes; to keep a change for
everyone, export the JSON (*Export* → *Export as JSON*) into that file. New dashboards can be saved as well.
Reset Grafana to the repository state:
`docker compose -f infra/docker-compose.yml rm -sf grafana && docker volume rm vf_grafana-data`.

At simulation speed 2×/4× the UNS timestamps run ahead of the clock; use a time range that ends in the future
(e.g. `now-15m` to `now+15m`) or switch back to 1× (O43).

## Orders (ERP simulator)
The ERP simulator at http://localhost:8098 is the planning level above the MES (ADR-0025). Its status page lists the
production orders with state and confirmed quantities and the component batches; you can create an order there
(*Create order* / *Create and release*) or switch the automatic release off.

- An order (`PO-<year>-<seq>`, material PC3280, quantity, due date) is **released** to the MES as BPMN message
  `OrderReleased`: a *Production order (MES)* process starts in Operaton (Cockpit shows it), starts the line and
  follows the progress. Only one order runs on LINE01 at a time; further orders wait as *Created*.
- The MES **confirms** progress (good, scrap) while the order runs and at the end the consumed component batches
  per lot (e.g. 9 × barrel L2609-0418). The ERP books them on its batch list; a batch it had no goods receipt for
  is added from the consumption (`Source` = consumption).
- Purchased batches arrive with a **despatch advice**: when the first part is built from a new lot of a supplier,
  the MES reports the lot staged at the line, and the ERP posts the goods receipt with the supplier's quantity
  (`Source` = despatch-advice). The column *Supplier batch* links the despatch advice to the supplier's batch AAS
  and its 3.1 material certificate and shows the batch footprint.
- **The line keeps running**: when no order is open, the ERP releases the next queued order or a *standing order*
  of 48 parts. At the end of each order the line stops and restarts a few seconds later with the next one.
  Switching the automatic release off leaves the line stopped after the current order (or release orders by
  hand); the factory itself still auto-starts without the IT stack (offline training).

```bash
curl -s -X POST localhost:8098/api/orders -H 'Content-Type: application/json' -d '{"quantity": 12}'
curl -s localhost:8098/api/orders | jq '.[] | {ID, RequestState, Progress: .Progress | {Good, Scrap}}'
curl -s -X POST localhost:8098/api/goods-receipts -H 'Content-Type: application/json' \
  -d '{"material": "5032-1006", "lot": "DTS-2608-1173", "quantity": 500}'
```
All endpoints: [interfaces/services.md](interfaces/services.md#erp). ERP data is kept in memory like the BPMN engine;
after an ERP restart it takes over the order the MES is running.

## Alarms and events
The alarms service (http://localhost:8099, ADR-0026) manages the PLC alarms after ISA-18.2: every alarm has a
priority (Critical, High, Medium, Low), a state and a history, and every operator action is recorded.

| State | Meaning |
|---|---|
| UNACK | active, not yet acknowledged - needs attention |
| ACKED | active, acknowledged |
| RTNUN | gone again, but nobody acknowledged it |
| SHLVD | shelved by an operator for a limited time (at most 8 h), not shown as new |
| DSUPR | suppressed by design: a consequence of another alarm (e.g. the robot's protective stop while the E-stop is pressed) or meaningless in the current line state |

- **Acknowledge** on the HMI: the alarm line has an *Ack (n)* button (n = unacknowledged alarms); it acknowledges
  all of them as operator `HMI01`. The button is hidden when the alarms service is not running.
- Over REST: `curl -s localhost:8099/api/alarms | jq` (current alarms),
  `curl -s -X POST localhost:8099/api/alarms/201/ack -H 'Content-Type: application/json' -d '{"operator": "trainer"}'`,
  shelve: `.../api/alarms/302/shelve -d '{"operator": "trainer", "durationS": 600, "comment": "sensor cleaning"}'`.
- **Journal**: `GET /api/journal` (alarm transitions with operator and comment) and `GET /api/events` (every UNS
  event, command, command acknowledgement, PackML state change and session start).
- **Dashboard** *Alarms & events* in Grafana (http://localhost:3002/d/vf-alarms-events): standing and
  unacknowledged alarms, alarms per 10 minutes against the EEMUA 191 benchmarks (≤ 1 acceptable, > 10 = alarm
  flood), mean time to acknowledge, current alarms, top 10 bad actors, priority distribution, chattering and stale
  alarms, alarm journal, UNS event journal and events per minute.
- Training: start a scenario (F1 menu) or open the fence door - the alarm appears as UNACK, acknowledge it on the
  HMI, watch it return to normal and look at the journal in Grafana.

## Predictive maintenance
The fingers of the robot gripper GR01 wear with every grip (ADR-0029). The gripper reports its jaw offset
(`finger_wear`, limit 1.0 mm), grip force, closing time, grips and regrips - visible in the inspector (click the
robot: RB01 → OperationalData) and in Grafana. At design wear the fingers last about 2.5 million grips; the
training scenario **Gripper finger wear** (F1 menu → scenarios, or `--vf-scenario=gripper_wear`) makes them wear
out within a few minutes.

1. **Watch** the dashboard *Maintenance* (http://localhost:3002/d/vf-maintenance): health index, remaining useful
   life (grips and hours, conservative 90 % lower bound), finger wear against the limit, grip force and closing
   time. The maintenance service (http://localhost:8094/api/components/GR01) evaluates the history every 10 s;
   after about 5-6 grips the wear trend is significant.
2. **Maintenance order**: when the lower bound of the remaining life drops below 8 h (one shift) the service opens
   the BPMN process *Maintenance order* (MO-…) and raises the advisory alarm **901** (priority Low; acknowledge it
   on the HMI). The task *Plan maintenance: Gripper fingers GR01* appears on the **MES terminal** and in the
   Operaton Tasklist with the prognosis. Leave *immediate* off to keep the running production order (the line
   stops at the next order boundary - the ERP releases no new order until the maintenance is done), or tick it
   to stop now.
3. At the order boundary the line stops in the unit mode **Maintenance** (HMI: mode, no infeed). The task
   *Replace gripper fingers (GR01)* lists the steps, spare part and tools from the AAS MaintenanceInstructions.
   Enter technician and findings and complete it: the wear diagnostics of the gripper are reset through the line
   controller's Control Component (the inspector shows `finger_wear` 0, `grip_cycles` 0), the line returns to
   Production and the next order starts the line.
4. **Record**: GR01 → *ConditionMonitoring* shows health, RUL, recommendation and the *MaintenanceRecords*
   (order, technician, grips achieved, downtime); *Reliability* gets the observed field data set; alarm 901
   returns to normal.

Without the IT stack (or without maintenance) the parts start to slip above 85 % of the wear limit, the robot
regrips and finally reports a fault (alarm 202, line held). Thresholds: `PUT localhost:8094/api/settings
'{"rulHoursThreshold": 8, "healthIndexGate": 0.85, "healthIndexOrder": 0.25}'`; shorter orders for a quick demo:
`curl -X PUT localhost:8098/api/settings -d '{"standingQuantity": 4}'`.

## Sustainability (carbon footprint)
The sustainability service (http://localhost:8097, ADR-0025) writes the carbon footprint into every packed part's
passport (CarbonFootprint submodel: total, purchased components, manufacturing with energy and loss shares) and
keeps the energy/CO₂e values of the devices and the line up to date. `curl -s localhost:8097/api/kpis | jq` shows
the session figures (average PCF of a good part, energy per good part, production losses, line energy);
`/api/footprints/<serial>` the breakdown of one part including the component batches and where their footprint
came from: for the five purchased components the supplier's batch-specific value from the batch AAS in the
supplier environment (`dataQuality` primary), otherwise the declared value of the component type (secondary).
The passport states the data quality: `PrimaryDataShare` (PACT primary data share) and, for the purchased
components, `SupplierSpecificDataShare`; the KPIs average both.

## Suppliers and batches
The suppliers of the end caps, seal kit, screws and protective cap publish their data in their own AAS environment
(http://localhost:8191, ADR-0028), separate from the plant's (8091): one AAS per company (company data, contacts),
one per product type as the supplier sells it, and one per delivered batch (batch information, carbon footprint of
the batch, material composition, inspection certificate 3.1 per EN 10204 as PDF). The plant keeps its own view of
the purchased parts (`CMP_*`, customer part numbers) and links both by the GTIN.

- A batch AAS appears when the batch is delivered: the first part built from a new lot triggers the goods receipt
  in the ERP, which fetches the supplier's despatch advice; the supplier portal publishes the batch AAS with it.
- In the passport of a part, the as-built BoM node of a purchased component carries the batch's GS1 Digital Link
  (`…/01/<GTIN>/10/<lot>`). In the AAS inspector, select the node (e.g. *Protective cap, batch KTW-26-0911*) and
  press *Open asset AAS*: the inspector finds the batch AAS in the supplier environment via discovery, like any
  other AAS; *Open type AAS* then shows the supplier's product type.
- By hand: `curl -s localhost:8190/api/despatch-advices | jq '.[].BatchAsset'`, or with the BaSyx web UI pointed at
  http://localhost:8191. Developer option: `--vf-inspect=https://virtual-factory.example/01/04099994010016/10/KTW-26-0911`.

## Product passports (DPP API)
Every cylinder gets an item-level digital product passport while it is produced (its workpiece AAS, ADR-0021): as-built
technical data (leak rate, stroke times, cap colour), the component batches it was built from (reported by the
assembly cell; each feeder changes its batch after its own number of parts), material composition and recycled
content per batch, carbon footprint (written by the sustainability service right after packing), contacts incl.
take-back, and - for packed good parts - an *inspection
certificate 3.1* PDF plus the data sheet, manuals and the REACH SVHC information. Rejects get the documents but no
certificate; their passport is `Inactive`, like the passport of a part still in production. A packed good part's
passport is `Active` and **stays available after you restart the factory** (new session); parts that were not
shipped (rejects, lost or unfinished parts) are removed at the next session start. Serial numbers continue across
factory runs (stored in Godot's user data, `retain.json`), so a passport is never overwritten; `--vf-serial-start=<n>`
sets the next serial.

**QR code and resolver.** The type plate of every cylinder carries a QR code with its GS1 Digital Link
`https://virtual-factory.example/01/04099999032808/21/<serial>` (its globalAssetId). Real phones cannot resolve
the `.example` domain, so the inspector action *Scan QR code (open passport)* puts the link's path onto the local
GS1 resolver (`resolver_url` in `godot/config/backend.json`, default http://localhost:8096). The resolver
redirects to a passport page with the public sections (en/de; switch at the top right). Machine clients get all
links as a linkset:
```bash
curl -s -H 'Accept: application/linkset+json' \
  http://localhost:8096/01/04099999032808/21/PC3280-2026-000005 | jq '.linkset[0] | keys'
curl -si 'http://localhost:8096/01/04099999032808/21/PC3280-2026-000005?linkType=gs1:certificationInfo' | grep -i location
```
To scan a QR code from a screenshot: decode it with any QR app and replace `https://virtual-factory.example` with
`http://localhost:8096`.

![QR code on the type plate](screenshots/m9-qr.png)
![Passport page of the resolver](screenshots/m9-passport.png)

Or read the passport with the BaSyx DPP API:
```bash
enc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
curl -s "http://localhost:8093/v1/dppsByProductId/$(enc https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000005)" | jq .
```
More examples (by DPP id, single element, find all parts with a given batch):
[interfaces/services.md](interfaces/services.md#dpp-api). Passports of shipped parts are kept until the stack is
stopped with `down` (the AAS database is on tmpfs, O53).

## Training UI (M5)
Everything an operator needs is in the 3D scene (world-space panels, ready for VR later):
- **AAS inspector:** click any device (or the control cabinet for PLC01, or a cylinder on the belt or in a KLT)
  to open its AAS in front of you: thumbnail, submodels, element tree. The visible submodel updates live when
  BaSyx reports a change (MQTT event → fetch). *Open type AAS* jumps from an instance to its type. For a KLT the
  inspector offers the exchange (completes a pending *Exchange KLT* task, otherwise exchanges directly); for a
  cylinder *Scan QR code (open passport)* opens the passport page of its Digital Link in the browser. The
  inspector finds every AAS like a real client: asset id (Digital Link of the part, asset id of the device) →
  discovery → registry → endpoint (ADR-0023), in the plant's and the suppliers' environment (`aas_registries`).
  Selecting an element that stands for another asset (a BoM node) shows *Open asset AAS* (e.g. a supplier batch).
- **HMI** (stand left of the conveyor): PackML state, Reset/Start/Stop/Hold/Unhold/Suspend/Unsuspend/Abort/Clear
  (only allowed commands are enabled), parts, reject rate, OEE (availability × performance × quality), automatic
  KLT exchange on/off and manual exchange. The HMI talks to the PLC directly (fieldbus), like a real panel; the
  *Ack (n)* button next to the alarm text acknowledges the alarms in the alarms service (see *Alarms and events*).
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
`--vf-inspect=<AAS tag | serial | asset id>`, `--vf-estop=1` (press the E-stop), `--vf-scenario=<id>`, `--vf-ui=off`, `--vf-xr` (OpenXR headset, see
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
uv run -m provisioner check --data supplier --blueprints   # supplier data set (aas/data/supplier, ADR-0028)
uv run -m provisioner upload --data supplier # into a running supplier environment (8191)
uv run tools/check_aasx.py                   # IDTA aas-test-engines on all packages (plant + supplier)
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
