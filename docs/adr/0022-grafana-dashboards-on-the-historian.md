# ADR-0022: Grafana dashboards on the historian (SQL via Flight SQL), anonymous read-only

- Status: accepted
- Date: 2026-10-03

## Context
The historian (ADR-0019) records every UNS value of a session in InfluxDB 3 Core, but the only ways to look at it
were SQL over HTTP and the AAS TimeSeries LinkedSegment. Trainers and learners want a live process view (state,
output, quality, energy) next to the 3D factory, without accounts for every viewer, while trainers must be able to
adapt the dashboards.

## Decision
- **Grafana OSS** `grafana/grafana:13.2.3` as compose service `grafana`, host port 3002. Configuration in
  `infra/grafana/` (read-only mounts): `grafana.ini`, provisioning of the data source and the dashboard provider,
  the dashboard JSON `dashboards/line01-live.json` (source of truth) and a small entrypoint wrapper.
- **Data source**: Grafana's built-in InfluxDB data source in query language **SQL** (Flight SQL over gRPC on the
  HTTP port `http://influxdb3:8181`, `insecureGrpc: true`, database `vf`). Grafana's SQL mode requires a token;
  InfluxDB runs `--without-auth` and accepts any value (`without-auth`). Tested with InfluxDB 3.12.0 Core:
  health check OK, `$__timeFilter`, `$__timeFrom/$__timeTo`, window functions (`lag`, `lead`, `max() OVER`),
  `date_bin`, CTEs, scalar subqueries and `UNION ALL` work. The plugin bundled in the image (InfluxDB 13.1.5) is
  used; downloading/auto-updating plugins at start (`[plugins] preinstall`) is disabled - reproducible and offline.
- **Access**: anonymous access with role Viewer in the organisation "Virtual Factory" (read-only, no Explore, no
  saving); login form enabled with the local accounts `admin` and `editor` (role Editor), both with the documented
  local default password `virtualfactory` (open issue O34). No sign-up, no telemetry, update checks, news feed or
  external snapshots. The organisation name, the `editor` account and the home dashboard (`LINE01 live`) cannot
  be expressed in file provisioning; the entrypoint wrapper sets them through the HTTP API after start
  (idempotent, failures are only logged).
- **Editing**: the provisioned dashboard has `allowUiUpdates: true`. Logged-in editors save in place; the edit lives
  in the named volume `vf_grafana-data` (with users) until the JSON file in the repository changes, then the file
  wins again. Permanent changes are exported (Share → Export) into `infra/grafana/dashboards/`. New dashboards can
  be created and saved freely by editors.
- **Dashboard "LINE01 live"** (uid `vf-line01-live`, refresh 5 s, last 15 min): only real historian columns
  (see [user-guide](../user-guide.md#dashboards-grafana)). Sparse rows (a field is only set when it changes) are
  handled in SQL: state timelines add the last change before the range and the current value at its end; power
  and air flow are derived from the cumulative counters (`energy` kWh → W, `air_consumption` Nl → Nl/min) per
  10 s; counters use the session's last value. Variable `session` with the entry `latest`, resolved by the hidden
  variable `sid` to the newest session on every time-range refresh. OEE is computed like the HMI (no OEE in the
  PLC): availability from PackML state durations, performance with the AC01 default takt of 12 s, quality from
  the counters.
- The training UI menu has an entry *Open dashboard (Grafana)* (`backend.json` `grafana_url`, `OS.shell_open`).

## Alternatives
- **InfluxQL v1 compatibility** (`/query`) of InfluxDB 3: works without gRPC, but InfluxQL lacks window functions,
  CTEs and subqueries needed for counters, OEE and state look-back; SQL is also what the AAS LinkedSegment uses.
- **Grafana "Infinity"/JSON API on `/api/v3/query_sql`**: needs a community plugin download and loses the
  time-series semantics of the native data source.
- **No persistence** (Grafana state only in the container): would lose editor changes and users with every
  re-creation; the Node-RED sandbox follows the same pattern (named volume, repo provisioning as baseline).
- **Read-only provisioned dashboard + "Save as" copies**: cleaner separation, but the user requirement is that the
  dashboard itself is editable when logged in.

## Consequences
+ Live process view for every visitor without login, consistent with the AAS (same historian, same columns).
+ Dashboard as code in the repository; data source and dashboard survive restarts and `down`.
− One more container (~450 MB image). Local default passwords (O34); anonymous viewers can run arbitrary read
  queries through the data source proxy (InfluxDB has no auth anyway).
− UNS timestamps are simulation time: at 2×/4× speed they run ahead of the wall clock, so data appears "in the
  future" of a relative time range (O43). The OEE performance uses the default takt, not a changed `takt_time` (O42).
