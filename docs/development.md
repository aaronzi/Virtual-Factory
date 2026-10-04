# Development and CI

Checks that must pass before a commit are listed in [CLAUDE.md](../CLAUDE.md#rules) and the
[user guide](user-guide.md#developer-commands). This page describes the continuous integration and how to run
the integration suite against the full stack.

## CI workflows

| Workflow | Trigger | Content |
|---|---|---|
| `CI` ([ci.yml](../.github/workflows/ci.yml)) | push to master, pull requests | Python unit tests, architecture and complexity checks, interface catalogue, gdlint; GUT tests and a 300 s headless line run (UNS off) |
| `Integration` ([integration.yml](../.github/workflows/integration.yml)) | push to master, manual (`workflow_dispatch`) | full compose stack + UNS-linked headless factory, `pytest -m integration`; a skipped test fails the job (~8 min of stack run locally; budget 75 min) |

Both check out with Git LFS (the AASX packages and Godot assets are LFS files).

## Integration suite

```bash
tools/ci_integration.sh                 # what the Integration workflow runs; tears the stack down afterwards
VF_CI_KEEP=1 tools/ci_integration.sh    # leave the stack running (default profile + CI overrides)
tools/ci_integration.sh -k alarms       # extra arguments go to pytest (the skip check still applies)
```

The script owns the compose project `vf` and its host ports: it replaces a running stack (`down`, fresh tmpfs
databases), so do not run it in parallel with another stack or a UNS-linked Godot. Steps:

1. **Stack**: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.ci.yml up -d`. The
   [CI override](../infra/docker-compose.ci.yml) sets the ERP standing order to 2 parts (the order and
   maintenance tests never wait behind a 48-part order), adds healthchecks (MQTT, InfluxDB, Operaton,
   Grafana, ops gateway, resolver, plc-comm) and leaves the AAS Web UI out (profile `ui`).
2. **Readiness gate** (`uv run tools/ci_integration.py stack`): all containers running/healthy, one-shots
   exited 0, AAS and supplier preload imported, BPMN models deployed by the MES, ops gateway endpoints
   resolved from the AAS (OPC UA), every service `/health` answers.
3. **Factory session 1**: headless Godot (`--headless --max-fps 60 --path godot -- --vf-quit-after=180`) with
   the default UNS (`ws://localhost:9001`) and PLC backplane (`tcp://localhost:4841` → plc-comm). Godot quits
   by itself (SIGTERM would skip saving the retentive serial counter); then a packed part's passport must be
   Active.
4. **Factory session 2** for the tests, gate `factory`: UNS status online, PLC CPU linked (OPC UA
   `CpuConnected`), a passport older than the session start (retention test), a footprint with supplier
   primary data, a GR01 prognosis, a historian session, alarm 201 in NORM.
5. **pytest** `-m integration -rs --junitxml` (locally ~3 min, hard limit 50 min; the longest tests wait for production:
   order → confirmation ≤ 10 min, maintenance loop ≤ 12 min), then the **skip check**
   (`ci_integration.py skips`): every skip fails the run unless listed in `VF_CI_ALLOW_SKIP`.
6. Logs: `build/ci-integration/` (`compose.log`, `ps.txt`, `godot-session{1,2}.log`, `junit.xml`); the
   workflow uploads them as artifact `integration-logs` when the job fails.

Environment: `GODOT_PATH` (Godot 4.7.2 binary), `VF_CI_NO_BUILD=1` (use an existing `vf-services:dev`;
the workflow builds it with the buildx layer cache), `VF_CI_SESSION1_S`, `VF_CI_ARTIFACTS`.

Running single integration tests by hand against a running stack and factory is still possible
(`uv run pytest -m integration services/alarms`); without a producing factory most of them skip.

### Linux and macOS

- The services reach each other on the compose network; Godot on the host uses the published ports
  (localhost) only - no `host.docker.internal` is needed in either direction.
- All databases are on tmpfs (no host-path data volumes, no uid issues). The only host-path writes are the
  provisioner outputs `infra/basyx/preload*/` (root-owned files on Linux; delete them with
  `docker run --rm -v $PWD/infra/basyx:/b alpine rm -f /b/preload/*.aasx` if needed).
- Godot keeps the retentive serial counter in its user directory (`~/.local/share/godot/app_userdata/` on
  Linux, `~/Library/Application Support/Godot/app_userdata/` on macOS): serials continue across runs, so a
  serial is never reused while the AAS database survives.

## Godot exit leak check

The CI integration run fails if the first (cleanly quitting) factory session reports leaked objects or resources at
exit. Typical cause: a lambda that touches members of a RefCounted object (e.g. `UnsGateway`) connected to a signal
of an object it owns - the lambda captures `self`, the two keep each other alive and with them the co-simulation
master and all device models. Connect such signals to methods instead. Locally: `godot --verbose --path godot --
--vf-quit-after=20` and look for "Leaked instance" / "Resource still in use" at the end of the output.

## CI workflows and dependency updates

| Workflow | Runs on | Triggered by changes to |
|---|---|---|
| `ci.yml` | push to master, pull requests, manual | code, AAS data, config, infra (not Markdown, `docs/` except the generated device catalogue and the dependency rules, `blender/`, other workflows); the Godot job only for `godot/**` and its test scripts (`dorny/paths-filter`) |
| `integration.yml` | push to master, manual | everything that can affect the running stack (not docs, Blender sources, GUT test files, other workflows) |
| `markdown.yml` | push to master, pull requests, manual | `**/*.md`, `.markdownlint-cli2.yaml`, `lychee.toml` |

All workflows cancel a running job of the same branch when a newer commit arrives. Markdown checks locally:

```bash
npx --yes markdownlint-cli2
```

```bash
lychee --config lychee.toml --no-progress "./**/*.md"
```

`markdownlint-cli2 --fix` applies the safe fixes. Style: `.markdownlint-cli2.yaml` (prose lines ≤ 120 chars, tables and
code blocks exempt, `-` for lists, `<a id>` anchors allowed). Links: `lychee.toml` (offline, relative links and
anchors).

Dependabot (`.github/dependabot.yml`) checks weekly: GitHub Actions, the uv workspace (`pyproject.toml`/`uv.lock`),
the services' Dockerfile and the images in `infra/docker-compose*.yml` (BaSyx images grouped). `GODOT_VERSION` in the
workflows and the vendored GUT addon are updated manually.
