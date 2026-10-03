# Virtual Factory – notes for Claude

Plan and decisions: `docs/PLAN.md`. Architecture: `docs/architecture/README.md` (arc42) + `docs/adr/`.

## Commands
- Backend: `docker compose -f infra/docker-compose.yml up -d` (project `vf`; ports 8091 AAS env, 3001 UI, 1883/9001 MQTT).
  Do NOT touch the separate `rebac-*` containers (other project on 8080/8082/3000).
- GDScript tests: `tools/run_godot_tests.sh` · Python tests: `uv run pytest` (`-m integration` needs the stack)
- Checks (must pass before commit): `uv run tools/arch_check.py`, `uv run tools/complexity_check.py`,
  `(cd godot && uv run gdlint .)`
- Screenshot: `tools/screenshot.sh docs/screenshots/<name>.png [delay] [res://scene.tscn]`
- After adding/renaming Godot files: `(cd godot && /Applications/Godot.app/Contents/MacOS/Godot --headless --import)`

## Rules
- Module dependency rules in `docs/architecture/dependency-rules.yaml`: `core` depends on nothing; other modules
  only on `core`; `devices/<type>` isolated from each other; `factory` is the only composition root.
- Limits: file ≤ 300 lines, function ≤ 40 lines, line ≤ 110 chars. Exceptions need an inline reason.
- Device behaviour = `Fmi3CoSimulation` subclass + FMI 3.0 `modelDescription.xml`; no scene-tree access in models.
- Godot is Y-up, 1 unit = 1 m, SI units everywhere.
- 3D assets are produced by scripts in `blender/scripts/` (run through the Blender MCP), exported as .glb.
- Keep docs (requirements status, interfaces, open issues) in sync with code changes.
