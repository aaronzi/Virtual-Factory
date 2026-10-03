# ADR-0025: Service decomposition - sustainability service, ERP order simulator, persistent passports

- Status: accepted
- Date: 2026-10-03

## Context
`services/mes` had grown into a monolith: workpiece AAS and passports, quality, KLT contents, ISO 22400 KPIs, BPMN
workers and message correlation, but also the production-based product carbon footprint (historian energy,
allocation, losses) and the plant energy/CO₂e values. Production orders existed only as a Tasklist form; nothing
above the MES (ERP) released orders or received confirmations. Every new simulation session deleted all workpiece
AAS - also the passports of parts that had been packed as good parts, i.e. placed on the market. Real plants split
these responsibilities between systems with their own data ownership (ISA-95 levels 3/4), and a passport must
outlive the production session (ESPR: available for the product's lifetime).

## Decision
**Sustainability service** (`services/sustainability`, port 8097) owns the product carbon footprint:
- It executes the new BPMN service task `pcf-calculate` of WorkpieceLifecycle, placed directly after the MES task
  `workpiece-record-packing` (external task pattern, ADR-0016). Chosen over a UNS subscription to `part_sorted`
  and over BaSyx change events: the task runs only after the MES has written the packed workpiece AAS (no race on
  the shell), it receives all process variables (session, release/sort times, container, component lots), and
  failures are retried and become visible incidents in Cockpit. The MES does not call the service - the process
  model orchestrates both, they share no code but `vf_common`.
- It computes the PCF as before (method aas-model.md §6a; `carbon.py`, `allocation.py`, `process_energy.py`
  moved from the MES) and writes the **CarbonFootprint submodel** of the workpiece itself (built from the
  blueprint section, strictly validated, concept descriptions uploaded, reference added to the shell). The MES
  lists the CarbonFootprint semantic id in the DPP content of the packed stage (it composes the passport) and
  keeps foreign submodel references when it replaces the shell.
- Purchased components (A1) come through the interface `SupplierFootprints.footprint(bom_line, batch)`: default
  source today `ComponentTypeFootprints` (CarbonFootprint of the component type AAS, same value for every batch);
  the supplier AAS environment of phase B2 implements the same interface with batch-specific values and is chained
  in front (`ChainedFootprints`), so batches without a supplier record keep the declared average.
- Plant energy/CO₂e (OperationalCO2eq per device, LINE01 totals, MeasurementStart per session, energy intensity as
  PCF fallback) moved with it; session KPIs (average PCF of a good part, A1/A3 shares, energy per good part,
  production losses) on `GET /api/kpis`, footprints per part on `GET /api/footprints[/{serial}]`.

**ERP order simulator** (`services/erp`, port 8098): production orders (`PO-<year>-<seq>`, material PC3280,
quantity, due date) as ISA-95/B2MML-like JSON (OperationsRequest), released to the MES as BPMN message
`OrderReleased` (new message start event of ProductionOrder, business key = order number; the Tasklist start stays
for manual orders). The MES confirms InProcess on start/progress and Completed in the new task `order-confirm`
with good quantity, scrap and the actual consumption per component lot (OperationsPerformance,
MaterialConsumedActual - lots from `part_released`). The ERP books the consumption against batches; a lot consumed
before its goods receipt gets a retroactive receipt from the backflush (`Source = consumption`); goods receipts can
also be posted via REST. Batch records carry an empty `SupplierCertificate` for phase B2. Minimal status page at `/`.

**Order policy - the line keeps running**: the MES produces against released orders, the PLC keeps its auto start
(offline training without the IT stack must work). The ERP keeps exactly one order per line released: when
nothing is open, the oldest Created order is released, otherwise a *standing* make-to-stock order of
`VF_ERP_STANDING_QTY` (48) parts. At order completion the MES stops the line (ProductionOrder), the next release
restarts it within seconds. Releasing while an order is open is refused (one order at a time). ERP state is in
memory like the engine's H2: at start the ERP adopts the ProductionOrder instances the MES still runs, and an open
order without a running instance (engine restarted) becomes Aborted. Order tasks of the MES retry every 15 s for
an hour (line or ERP not reachable) before an incident; a new simulation session resets the PLC counters, the MES
rebases the order baseline so the progress is kept.

**MES keeps** production execution: order execution (ProductionOrder workers), workpiece AAS and passports,
quality verdict, KLT contents, ISO 22400 KPIs, event discovery and message correlation. No PCF, no InfluxDB.

**Persistent passports**: the DPP status follows the life of the unit - `Inactive` while in production and for
rejected or lost units, `Active` once a good unit is packed (shipped); `Archived` is reserved for the end of life.
On a new session the MES deletes only session data (units not shipped) and keeps every `Active` passport
(determined from one query over all DppMetadata submodels, so it also works after an MES restart);
`VF_RETENTION` (500) limits the rolling window of session data, `VF_PASSPORT_LIMIT` (0 = unlimited) optionally the
shipped passports. Policy recorded in LINE01/DataRetentionPolicies (`ProductPassportShippedUnits`, P10Y) and the
document VFP-DRP-2025-03 rev. 1.1. Because ids derive from the serial number, serials must never repeat: the AC01
serial counter is **retentive** in live sessions (Godot `RetentiveCounters`, `user://retain.json`, applied as the
fixed parameter `serial_start`; `--vf-serial-start`, `--vf-retain=off`; runs with `--vf-uns=off` stay
deterministic), and the MES refuses to overwrite the passport of a shipped unit with a new stage (task fails,
incident).

## Alternatives
- **PCF on `part_sorted` (UNS)**: fully decoupled from BPMN, but races with the MES writing the packed AAS and
  needs the release data cached per serial; failures would be invisible.
- **PCF on BaSyx change events** (packed ExecutedProcesses): the AAS as integration point, but no session or lots in
  the event, an extra read per part, and the same ordering problem with the shell reference.
- **MES calls the sustainability service (REST)**: simple, but couples the MES to it and puts PCF failures into
  the MES task.
- **ERP pushes orders to an MES REST API**: realistic too; the BPMN message start keeps the MES API surface at the
  engine (already the MES's process interface) and makes the release visible in Cockpit.
- **MES without orders (line always free-running)**: no realistic confirmations or traceability per order.
- **ERP in its own database**: survives restarts but diverges from the in-memory engine after `down`; adoption of
  running instances keeps both consistent at the same cost.
- **Unique serials from wall clock or MES assignment**: wall-clock ranges collide in faster-than-real-time runs;
  MES serial assignment (serialization service) is the realistic target but changes the cell interface.

## Consequences
+ Clear ownership: MES - workpiece AAS/passport composition; sustainability - CarbonFootprint and energy values;
  ERP - orders and batches. Phase B2/B3 plug in behind existing interfaces (SupplierFootprints, the external-task
  pattern).
+ Passports of shipped parts survive sessions and are served by the DPP API; rejects/lost units are cleaned up.
+ Orders with confirmations and lot consumption close the loop ERP ↔ MES ↔ line.
− Two more services; the order stop/restart between standing orders is visible on the line (a few seconds).
− The AAS server grows with shipped passports (tmpfs DB, wiped with `down`; O53). Passports written before this
  change, or with serials reused by older builds, are not repaired automatically.
