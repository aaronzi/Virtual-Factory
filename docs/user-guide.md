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

## Developer commands
| Command | Purpose |
|---|---|
| `tools/run_godot_tests.sh` | GDScript unit tests (GUT, headless) |
| `uv run pytest` | Python unit tests |
| `uv run pytest -m integration` | Integration tests against the running stack |
| `uv run tools/arch_check.py` | Architecture conformance (≥ 95 %) |
| `uv run tools/complexity_check.py` | Function length limits |
| `(cd godot && uv run gdlint .)` | GDScript lint |
| `tools/screenshot.sh out.png [delay]` | Headless-free review screenshot |
