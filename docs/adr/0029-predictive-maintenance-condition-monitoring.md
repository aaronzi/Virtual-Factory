# ADR-0029: Predictive maintenance - wear in the device models, RUL from the historian, maintenance orders in BPMN

- Status: accepted
- Date: 2026-10-03

## Context

The device models never degraded: the line ran identically forever, the IDTA Reliability and
MaintenanceInstructions templates were vendored but unused, and maintenance existed only as an interval plan of
the robot (UR5E_TYPE). Predictive maintenance is a core Industrie 4.0 use case for training: a measurable
degradation, a prognosis that can be explained, a maintenance order that is planned around production, a
technician task, the confirmation of the part change to the machine and the record in the digital twin.

## Decision

**Degradation in the device model (FMI).** The fingers of gripper GR01 wear (abrasive pad wear, linear in the
grips after Archard). It lives in the robot FMU RB01 (`devices/ur5e/model/gripper_wear.gd`, pure, seeded) because
the gripper has no interface of its own. Smart-gripper diagnostics as FMI outputs: `finger_wear` (jaw position
offset at contact, m, encoder noise 3 µm), `grip_force` (clamping force, -30 % at the limit), `grip_close_time`
(longer travel, slower jaws), `grip_cycles`, `grasp_retries`, `gripper_fault`. Parameters `finger_wear_rate`
(tunable, design 4e-10 m/grip = limit after 2.5 million grips), `finger_wear_limit` (1 mm), `finger_wear_start`,
`grip_force_nominal`, `regrip_attempts`, `grip_retry_interval`, `seed`. No instant failure: parts slip only above
85 % of the limit (probability rising to 1 at 115 %); a slipped part is regripped, after `regrip_attempts`
slipped grips `gripper_fault` (and `fault` → PLC alarm 202, HOLD) is set and the grip is retried every 10 s until
it holds. The finger change is the input `gripper_maintenance_reset` (rising edge; UNS pulse command). The
scenario `gripper_wear` accelerates the wear 100 000-fold (training).

**Maintenance service** (`services/maintenance`, port 8094, `infra/maintenance.json`): every 10 s it reads the
component's history from the historian (SQL, rows of the session since the last part change, newest 200) and
computes

- health index HI = 1 - wear / limit;
- remaining useful life by a least-squares line wear = a + b · cycles (wear is linear in the cycles): RUL =
  (limit - fitted wear) / b, one-sided 90 % lower bound with b + 1.28 s_b, hours at the throughput of the last
  20 samples, predicted failure date (measurement time base), confidence = R² · min(1, n / 12);
- the trend is used only if it is significant (n ≥ 6, t = b / s_b ≥ 3); otherwise (new fingers, normal wear
  far below the measurement noise) the design rate limit / useful life (lower bound: B10 life) from the
  Reliability submodel, confidence 0.2 (method DesignRate).
It opens a maintenance order when the RUL lower bound is below 8 h (one shift) while HI < 0.85, or HI < 0.25, or
the device reports `gripper_fault`. Chosen over machine-learning models: a linear wear model with a prediction
bound is what maintenance planners can check by hand, and it is honest about its data (DesignRate when there is
no trend). Results are published to the UNS (`{root}/maintenance/{component}/{indicator}`, retained, new section
`maintenance` of uns.json) and recorded by the historian in table `maintenance` (tag `component`) - Grafana
dashboard **Maintenance** (uid `vf-maintenance`).

**AAS submodels and ownership** (GR01, after ADR-0025 each service writes only its own data):

- `Reliability` (IDTA 1.0, IEC 62683): design sets of the gripper unit and the finger set (useful life,
  B10, MTTF) - manufacturer data, provisioned; the maintenance service appends and owns the observed set
  `…FingerSetObserved` (mean achieved grips per finger change, B10 from a Weibull wear-out model with assumed
  shape 3) after each change.
- `MaintenanceInstructions` (IDTA 1.0): condition-based task MI-PG85-01 "Replace gripper fingers" (steps,
  spare part FS-PG85-V50, tools, 20 min, warning at 80 %) - provisioned, read by the service.
- `ConditionMonitoring` (custom template, YAML DSL): health state/index, indicator vs. limit (reference to the
  RB01 TimeSeries), RUL (cycles, hours, lower bounds, failure date, confidence, method, threshold), symptoms,
  recommendation (en/de), open order, `MaintenanceRecords` (order, task, technician, findings, cycles at the
  change, HI before, downtime). IDTA offers no condition/prognosis template; ExecutedProcesses is for production
  steps of a product and was not used for maintenance. Provisioned with the initial state, written only by the
  maintenance service (changed values only).

**Maintenance workflow** = BPMN process `MaintenanceOrder` (bpmn/maintenance_order.bpmn, deployed by the MES
with all models, business key `MO-<year>-<seq>`, external tasks executed by the maintenance service):
plan (user task: next order boundary or immediately) → ERP maintenance window → wait until the window is active
→ LineControl `ExecuteSkill(Maintain, Maintenance)` → technician user task (steps from MaintenanceInstructions;
MES terminal or Tasklist) → `ExecuteSkill(Maintain, Maintenance, {"gripper_maintenance_reset": true})`, the
device confirms on the UNS → `SetUnitMode(Production)`, window completed → MaintenanceRecord + observed
Reliability, order closed.

- **ERP maintenance windows** (`erp/maintenance.py`): a capacity reservation like a PM order on the work centre.
  While one is open the ERP releases no production order; a window requested during an order becomes active
  at the order boundary (the MES stops the line at order end anyway); `Immediate` interrupts the running order,
  which the handback restarts with `ExecuteSkill(Produce, Production)`. Chosen over a hold in the MES (the ERP owns
  the release decision) and over stopping the line from the maintenance service at once (production loss).
- **Skill `Maintain`** of PLC01's Control Component Instance (modes: Maintenance; parameter
  `gripper_maintenance_reset`): the ops gateway stops the line if needed, applies the unit mode Maintenance and
  only then sends confirmation parameters to the endpoint `GripperMaintenanceReset` (AID action of RB01, MQTT).
  The device reset therefore travels AAS → ops gateway → Control Component → AID of the device - never directly.
- **LineControl `SetUnitMode`** (template revision 1.2, OPC 30050 SetUnitMode): mode change without a skill,
  needed to hand the line back in Production before the next order starts.
- **Advisory alarm 901** (priority Low, class Diagnostic, source MAINTENANCE in infra/alarms.json): the service
  publishes its alarm word on `{root}/maintenance/active_alarms`; the alarms service merges it with the PLC
  alarm word (ISA-18.2 life cycle, journal, acknowledgement on the HMI) - active while the order is open.

**Godot**: wear values in the inspector (RB01 OperationalData, generated), data-flow node "Maintenance"
(historian → maintenance → AAS / BPMN), training scenario `gripper_wear`.

## Alternatives

- **Degradation in the IT layer only** (simulated sensor values): no effect on the machine, no failure mode.
- **Wear model as a separate gripper FMU**: the gripper has no own controller or interface in the plant
  (TechnicalData: robot tool I/O); a separate FMU would need extra wiring for one grip event.
- **RUL by exponential degradation or particle filter**: no physical reason for non-linear pad wear; harder to
  explain; the linear fit with a lower bound is the standard first step (ISO 13381-1 trend-based prognosis).
- **Health/RUL only in the AAS**: no history for dashboards; the historian is the time-series store (ADR-0019).
- **Maintenance order in the ERP (PM module)** instead of BPMN: the MES/engine already runs operator tasks and
  is visible on the MES terminal; the ERP takes part through the maintenance window.
- **Alarm via the alarms REST API**: a second write path into the alarm server; the UNS alarm word keeps the
  alarm source decoupled exactly like the PLC.

## Consequences

- \+ Realistic loop with observable symptoms, a checkable prognosis, planning around production orders, operator
  tasks, a confirmed part change and the record in the twin; the Reliability and MaintenanceInstructions
  templates are now used with real content.
- \+ The line run and the other scenarios are unchanged (design wear 4e-10 m/grip).
- − One more service; ERP windows are in memory like the orders (O51). Wear state is not retentive: each Godot
  session starts with new fingers (O62). The prognosis covers one wear mechanism and a linear model; observed
  B10 values from an accelerated scenario are not field data (O63). No authentication on the maintenance API
  and task completion (O64, security phase).
