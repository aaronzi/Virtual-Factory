# ADR-0026: Alarm management after ISA-18.2 in an alarms & events service on TimescaleDB

- Status: accepted
- Date: 2026-10-03

## Context
The PLC of LINE01 raises alarms with PackML reactions (godot/control/sorting_line/line_alarms.gd), but the IT side
only saw `alarm_code`/`alarm_text` - the highest-priority alarm at the moment, no history, no acknowledgement, no
operator accountability and no alarm system performance figures. ANSI/ISA-18.2 (IEC 62682) and EEMUA 191 describe
what an alarm system has to provide: a rationalized master alarm database, a per-alarm state model with
acknowledgement, shelving and designed suppression, a journal of every transition and operator action, and KPIs
(alarm rate per operator, floods, standing/stale alarms, bad actors, chattering).

## Decision
- **Alarm source**: the PLC exposes its complete alarm word as the new FMI output `PLC01.active_alarms` (all active
  codes in priority order, e.g. `100,201`; empty when none) - published as UNS telemetry like every output, so
  consequential alarms hidden behind a higher one (E-stop → protective stop) are visible. `alarm_code` is used as
  a fallback until the alarm word has been received (older builds, other PLC paths).
- **Master alarm database** `infra/alarms.json` (rationalization): code, texts en/de, priority
  (Critical/High/Medium/Low from the PLC reaction and consequence), class, response time, consequence, remedy and
  designed suppression (`suppressed_by` consequential alarms, `suppress_in_states` PackML states). A unit test keeps
  codes, texts and priority order equal to the PLC table.
- **Service** `services/alarms` (port 8099): pure ISA-18.2 state machine (NORM, UNACK, ACKED, RTNUN, SHLVD - time
  limited to 8 h, DSUPR; out-of-service not used), inputs from the UNS (alarm word, `packml_state` for state-based
  suppression), operator actions over REST (acknowledge one/all, shelve, unshelve - operator name mandatory, comment
  optional), shelving expiry. It journals every alarm transition and **all UNS events, commands, command
  acknowledgements, PackML state changes and session births** (event journal). Current states are restored from the
  database at restart. Timestamps are the alarm server's receive time (UNS `ts` kept as `source_time`).
- **Storage: TimescaleDB** `timescale/timescaledb:2.30.2-pg17` as its own container `alarms-db` (not the BaSyx
  PostgreSQL), tmpfs like the historian (wiped with `down`), retention policies 90 days (alarm journal) / 30 days
  (event journal). Hypertables `alarm_journal`, `event_journal`; plain tables `alarm_definition`, `alarm_state`
  (updated in place), `alarm_occurrence` (one row per activation, acknowledged/cleared filled in later).
- **KPIs** (`GET /api/kpis`, Grafana): annunciated alarms per 10 min (average, peak), share of flood periods
  (> 10 per 10 min), standing and stale (> 1 h) alarms, top 10 bad actors with share, chattering (≥ 3 activations
  in 60 s), priority distribution, mean time to acknowledge / to clear.
- **Grafana**: built-in PostgreSQL data source `Alarms & events (TimescaleDB)` (uid `vf-alarms`, read-only role
  `grafana`, TimescaleDB mode) and the provisioned dashboard **Alarms & events** (uid `vf-alarms-events`).
- **HMI**: the alarm line of the operator panel got an *Ack (n)* button (unacknowledged count polled from the
  service, acknowledges all as operator `HMI01`); hidden when the service is not reachable. View passive, the
  controller in `factory/`, REST client in `connectivity/alarms`.

## Alternatives
- **ClickHouse**: excellent for high-rate append-only analytics, but ISA-18.2 needs state updates in place (alarm
  state, occurrence acknowledged/cleared), transactional upserts and joins with the master database at low event
  rates (a few per second); ClickHouse mutations and joins are awkward for that, and Grafana needs a plugin. Plain
  PostgreSQL with TimescaleDB gives hypertables, `time_bucket`, retention policies and SQL joins; Grafana reads it
  with its built-in data source.
- **Store in the historian (InfluxDB 3)**: no updates/joins, no transactional state; alarms are events, not series.
- **Store in the BaSyx PostgreSQL**: couples the alarm system to the AAS server's database lifecycle and schema
  migrations of BaSyx.
- **Derive alarms from `alarm_code` only**: loses all but the highest alarm; consequential alarms and their
  suppression could not be modelled.
- **OPC UA Alarms & Conditions** on the PLC's OPC UA server (ADR-0024): the standard way for a PLC to expose
  conditions; the alarm word over the UNS is protocol-independent today and the service can switch to A&C events
  later without changing its state model.

## Consequences
+ Operator accountability (who acknowledged/shelved when), a journal of the whole UNS event stream and KPIs
  comparable to EEMUA 191 benchmarks; suppression keeps an E-stop from flooding the operator with its
  consequences.
+ One more database container (~300 MB image) with its own retention; Grafana gets a second data source.
− Shelving and acknowledgement live in the IT alarm system; the PLC alarm itself is not acknowledged (no latching
  alarms in the PLC). No authentication: any client can acknowledge (local use, O34 pattern).
− Alarm times are receive times; with faster-than-real-time simulation they differ from the UNS `ts` (O54).
