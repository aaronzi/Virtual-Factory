# ADR-0019: Historian (InfluxDB 3 Core) referenced by IDTA TimeSeries LinkedSegments; slim AAS

- Status: accepted
- Date: 2026-10-03

## Context
Until M6 every FMI output was written into the device AAS (OperationalData process values, ~117 AIMC mappings,
robot joints and belt position at up to 10 Hz) and the MES kept a 30-minute power ring buffer as an IDTA TimeSeries
`InternalSegment` (one `PUT` of the whole segment per device every 10 s). This loaded the AAS server with values
nobody reads from the AAS (risk R5), the history was short and coarse (one power sample per 10 s), and the
instance PCF used a rolling line average, independent of what happened to the individual part (risk R9).

## Decision
- **Historian**: InfluxDB 3 Core (open source, `influxdb:3.12.0-core`, port 8181, no authentication, data on
  tmpfs = per session like the AAS DB; HTTP line-protocol writes and SQL queries `/api/v3/query_sql`). Its ~72 h
  query window of Core is irrelevant for per-session data. A Python service `historian` subscribes to the UNS
  telemetry of all devices and writes every sample with its UNS timestamp: one table per device (lower-case FMI
  instance name), one field per FMI output (type from the model description), tag `session`; batches of 0.5 s
  or 1000 lines, bounded retry buffer. Configuration in `infra/historian.json` (shared with provisioner and MES).
- **TimeSeries with LinkedSegment** (IDTA 02008-1-1, generated per device from the FMI model description):
  `Metadata.Record` = `Time` (semanticId `https://admin-shell.io/idta/TimeSeries/UtcTime/1/1`, `xs:dateTime`) +
  one Property per FMI output (idShort = variable = column, semanticId = the generated FMI process-value concept
  description with unit), no values; `Segments.LinkedSegment` `Historian` with `Endpoint`
  (`http://localhost:8181/api/v3/query_sql?db=vf&format=json`) and `Query` (SQL over the last hour). The UtcTime
  concept is specified in IDTA 02008-1-1 (Table 4/10) but not published in the IDTA SMT repository; the
  provisioner adds a concept description with the texts of Table 10 (isCaseOf IRDI `0112/2///61360_4#ADA387#001`).
  EnergyConsumption/`TimeSeries` references the submodel. The AAS no longer changes when data is recorded.
- **Slim AAS**: OperationalData process values and AIMC mappings only for outputs with FMI variability
  `discrete` (Boolean/Int32/String and per-event Float64 values such as QS01 `delta_e` or AC01
  `last_leak_rate`), plus OperatingState, OperatingHours and the EnergyConsumption values. Continuous signals
  (joint angles, TCP, belt position, gripper width, cycle progress) are described in the AID (interface
  unchanged) and recorded only by the historian. The bridge writes numbers at most every 5 s per element.
- **Production-based PCF** in the MES from historian data (method in [aas-model.md §6a](../interfaces/aas-model.md)):
  assembly-cell cycle energy, residence-time share of the downstream devices, compressed air split off and
  reported separately, production losses of rejects allocated to good parts; written as three CarbonFootprint
  entries (A1-A3 total, A1 components, A3 manufacturing with energy details).

## Alternatives
- TimescaleDB on the existing Postgres: SQL as well, but couples the historian to the BaSyx database and needs a
  schema per device; InfluxDB's schemaless line protocol matches "one field per FMI output" directly.
- Keeping `InternalSegment` records in the AAS: simple for AAS-only clients, but the write load grows with the
  sampling rate and the AAS server is no time-series store.
- `ExternalSegment` (files): suits handover of finished series, not a live session.

## Consequences
+ AAS write load drops (no 10 Hz signals, no ring-buffer PUTs); full-resolution history of every output.
+ The AAS still tells *what* is recorded (record semantics with units) and *where/how* to get it (Endpoint/Query).
+ The PCF reflects production: parts that waited on a held line carry more energy.
− Clients need to speak the database's API (InfluxDB SQL over HTTP); the LinkedSegment Query is DB-specific.
− One more container (634 MB image) and service; InfluxDB data is lost with `down` (intended).
