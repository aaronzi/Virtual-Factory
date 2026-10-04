# Virtual Factory – notes for Claude

Plan and decisions: `docs/PLAN.md`. Architecture: `docs/architecture/README.md` (arc42) + `docs/adr/`.

## Commands

- Backend: `docker compose -f infra/docker-compose.yml up -d [--build]` (project `vf`). Ports: 8091 AAS env,
  3001 UI, 1883/9001 MQTT, 8092 Operaton BPMN (demo/demo), 8093 BaSyx DPP API, 8094 maintenance, 8095 ops
  gateway, 8096 GS1 resolver, 8097 sustainability, 8098 ERP (status page), 8099 alarms, 8181 InfluxDB 3,
  3002 Grafana (anonymous read-only; admin/editor: virtualfactory), 4840 PLC01 OPC UA
  (`opc.tcp://localhost:4840/vf/plc01`), 4841 PLC backplane, 8190 supplier portal, 8191 supplier AAS env.
  Services in `services/`: bridge, mes, ops-gateway, historian, resolver, sustainability, erp, alarms (+ alarms-db
  TimescaleDB: `docker compose exec alarms-db psql -U vf_alarms alarms`), maintenance, plc-comm (PLC OPC UA server
  fed by Godot via the backplane; `--vf-backplane=off` = direct MQTT), edge (OPC UA → UNS), supplier (portal) +
  supplier-aas-env (second BaSyx environment; data in aas/data/supplier with `idBase` per company;
  `uv run -m provisioner check|build|upload --data supplier`).
  Grafana dashboards: infra/grafana/dashboards/*.json.
  Secure profile (ADR-0027): `docker compose -f infra/docker-compose.yml -f infra/docker-compose.secure.yml up -d
  --build` (Keycloak 8180, users/password in docs/architecture/security.md), back: `... -f infra/docker-compose.yml
  up -d --remove-orphans`; tests `uv run pytest -m secure`; Godot `--vf-secure`.
  Do NOT touch the separate `rebac-*` containers (other project on 8080/8082/3000).
- GDScript tests: `tools/run_godot_tests.sh` (also compiles every script) · line run: `tools/run_line_simulation.sh [s]`
  · training scenarios: `tools/run_scenarios.sh` · Node-RED sandbox: `--profile sandbox`
  · desktop builds: `tools/export_builds.sh [macOS|Windows|Linux]` → build/ (needs Godot 4.7.2 export templates)
- Python tests: `uv run pytest` (`-m integration` needs the stack; full CI run incl. stack + linked Godot:
  `tools/ci_integration.sh`, see docs/development.md) · interface docs: `uv run tools/gen_interface_docs.py`
- Checks (must pass before commit): `uv run tools/arch_check.py`, `uv run tools/complexity_check.py`,
  `(cd godot && uv run gdlint .)`
- Screenshot: `tools/screenshot.sh docs/screenshots/<name>.png [delay] [scene] --vf-camera=x,y,z,tx,ty,tz`
- GIF: `godot --path godot --write-movie <dir>/f.png --fixed-fps 15 --quit-after N` + `uv run tools/frames_to_gif.py`
- After adding/renaming Godot files: `(cd godot && /Applications/Godot.app/Contents/MacOS/Godot --headless --import)`

- AAS: `uv run -m provisioner check|build|upload [--only TAGS] [--blueprints]`, `uv run tools/check_aasx.py`,
  `uv run tools/aas_template_tree.py <Template-ver>`; data in aas/data (format: docs/interfaces/aas-model.md §7)
  · document PDFs: `uv run aas/scripts/make_documents.py [ID…]` · sample certificate: `uv run python -m mes.certificate`
- Product data shared by the type and the item passport: `aas/data/common/product_passport_pc3280.yaml`, included
  with `$include: "file#Key"`. DPP id = AAS id (BaSyx DPP API, ADR-0021).

## Rules

- Module dependency rules in `docs/architecture/dependency-rules.yaml`: `core` depends on nothing; other modules
  only on `core`; `devices/<type>` isolated from each other; `factory` is the only composition root.
- Limits: file ≤ 300 lines, function ≤ 40 lines, line ≤ 110 chars. Exceptions need an inline reason.
- RefCounted classes: connect owned objects' signals to methods, not to lambdas that touch members (the lambda
  captures self → reference cycle, the whole simulation leaks at exit; CI fails on Godot exit leak reports).
- Device behaviour = `Fmi3CoSimulation` subclass + FMI 3.0 `modelDescription.xml`; no scene-tree access in models.
- Godot is Y-up, 1 unit = 1 m, SI units everywhere.
- 3D assets are produced by scripts in `blender/scripts/` (run via Blender MCP: `exec(open(".../build_<asset>.py").read())`,
  all: `build_all.py`), exported as .glb; palette colours are sRGB. Animated/switched parts are separate named objects.
- Renderer is Compatibility (ADR-0010). Keep draw calls ≤ 450 incl. shadows (`--vf-perf-report=5 --vf-perf-warmup=170`).
- Long Godot runs from the shell: wrap in `perl -e 'alarm N; exec @ARGV' ...` (macOS can throttle background windows).
- Keep docs (requirements status, interfaces, open issues) in sync with code changes.
- UI (ADR-0018): `ui/` holds passive views only (world panels, inspector, HMI, terminal, menu); controllers live in
  `factory/`. Static UI texts are translation keys (`ui/i18n/ui.csv`, en+de). Panels re-render only when dirty.
- UNS contract: `godot/config/uns.json` (Godot gateway, AID generation and all services read it). BPMN models in
  `bpmn/` (deployed by the MES). Line commands only via LINE01 LineControl operations (delegated to ops-gateway).
- Clients resolve AAS via discovery + registry (ADR-0023, `vf_common.resolver`); `vf_common.ids` only mints ids.
- Service ownership (ADR-0025): the workpiece CarbonFootprint is written only by the sustainability service
  (`pcf-calculate`); orders are released only by the ERP (BPMN `OrderReleased`); `infra/alarms.json` mirrors
  `line_alarms.gd` (test). Shipped passports persist across sessions; serials never repeat (retentive counter,
  `--vf-serial-start`, `--vf-retain=off`).
- Security model only in `infra/security.yaml` → `uv run tools/gen_security_config.py [--check]`; never hand-edit the
  generated realm, ABAC rules or MQTT ACL files.
- AAS data: use IDTA templates (aas/templates/idta) where they exist; custom templates only in the YAML DSL with en/de
  texts. Quote YAML texts containing ',' or ':' in flow maps. Device interfaces (AID/AIMC) are generated - never hand-write.
