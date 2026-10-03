# Fault injection, PLC alarms and training scenarios

Training scenarios (FR-09) inject faults into the device FMUs through ordinary FMI inputs and tunable parameters.
The same variables can be written by a trainer, an agent or the AAS over MQTT (UNS commands, AID actions), so a
scenario, a human and an automated test all use one interface.

## Fault variables

| Variable | FMI | Type, range | Effect |
|---|---|---|---|
| `CV01.motor_fault` | input | Boolean | Drive (VFD) trips: belt coasts down with `coast_deceleration` (1.5 m/s²), power drops to standby, output `fault` = true until cleared |
| `QS01.contamination` | tunable parameter | Float64 0..1 | Dirty lens: perceived colour = lerp(surface, dark grey (0.16, 0.15, 0.13), value) before noise. Red cap: ΔE ≈ 14 at 0.2, 22 at 0.3, 38 at 0.5 (tolerance 25) → false rejects |
| `QS01.drift` | tunable parameter | Float64 -1..1 | Calibration drift: additive offset on all measured sRGB channels |
| `LB01/LB02.misalignment` | input | Float64 0..1 | Marginal received light: random beam dropouts (Poisson rate value · `dropout_rate` 1.5/s, each `dropout_duration` 0.06 s, seeded RNG `seed`, deterministic) → false triggers; at 1 the beam is lost permanently (signal stuck). `stability_ok` (IO-Link excess-gain diagnostics) is false from 0.2 |
| `AC01.defect_rate_missing_cap`, `AC01.defect_rate_wrong_cap` | tunable parameters | Float64 0..1 | Probability per part (layout defaults 0.05 / 0.03) |
| `RB01.protective_stop` | input | Boolean | Robot freezes in its current pose (job continues after release), output `protective_stopped`. Meant to be driven by the fence door (world interaction) |
| `RB01.finger_wear_rate` | tunable parameter | Float64 ≥ 0 (m per grip) | Wear of the gripper finger pads (design 4e-10). Symptoms: `finger_wear` (jaw offset, limit `finger_wear_limit` 1 mm), `grip_force` (-30 % at the limit), `grip_close_time` rises; above 85 % of the limit parts slip and are regripped (`grasp_retries`), after `regrip_attempts` (3) slipped grips `gripper_fault` → `fault` → alarm 202; reset by `RB01.gripper_maintenance_reset` (finger change, ADR-0029) |

All fault variables are listed in `commands.writable` of [`godot/config/uns.json`](../../godot/config/uns.json):
`{root}/{device}/cmd/{variable}` with `{"v": value}` (see [uns.md](uns.md)). Default values = no fault.

## PLC alarms (PLC01)

Inputs wired in the layout: `CV01.fault → PLC01.cv_fault`, `RB01.protective_stopped → PLC01.rb_protective_stop`
(plus the existing `rb_fault`, light barrier signals and the infeed tracking). Outputs: `alarm_code` (highest-priority
active alarm, 0 = none), `alarm_text`, `alarm_count` (alarms raised since start), `active_alarms` (alarm word: all
active codes in priority order, e.g. `100,201` - input of the ISA-18.2 alarm management, ADR-0026), `horn`.
Implementation: `godot/control/sorting_line/line_alarms.gd`.

| Code | Text | Condition | PackML reaction |
|---:|---|---|---|
| 100 | E-stop pressed: release it, then Clear and Reset | `estop` (emergency-stop button on the HMI stand latched; the safety circuit also stops the robot via `RB01.protective_stop`) | ABORT while active (Clear is refused until the button is released); operator: release, Clear, Reset |
| 101 | CV01 conveyor drive fault | `cv_fault` | ABORT while active (Clear is refused until the fault is gone); operator: Clear, Reset (auto_start then starts) |
| 202 | RB01 robot fault | `rb_fault` (rising edge) | HOLD; operator Unhold |
| 201 | RB01 protective stop (safety fence door open) | `rb_protective_stop` | HOLD while active, automatic Unhold when released |
| 302 | LB02 inspection light barrier blocked (signal stuck) | LB02 blocked > `sensor_blocked_timeout` (1.5 s) while the belt runs in WAIT_PART; latched until the beam is free | HOLD, automatic Unhold when the beam is free |
| 301 | LB01 infeed light barrier blocked (signal stuck) | LB01 blocked > `sensor_blocked_timeout` while the belt runs; latched until free | HOLD, automatic Unhold when free |
| 401 | Infeed timeout: released part not seen at LB01 | no LB01 detection within `infeed_timeout` (8 s) of belt running time after a release (also counts `infeed_faults`) | warning only; cleared by the next LB01 detection |

Priority = table order. Only automatic holds are released automatically; an operator Hold stays.
The PLC sequence keeps running in every PackML state, so work in progress (measurement, robot job handshake)
completes while the line is held or aborted; belt, cell and new robot jobs need EXECUTE.

Stack light SL01 (`devices/stack_light`, on the control cabinet) is driven by `light_green` (EXECUTE),
`light_amber` (Held, Suspended, Idle, acting states or a warning) and `light_red` (Stopped, Aborted or an alarm that
stops the line); `horn` drives the buzzer input (not audible).

## Scenario files

`godot/config/scenarios/*.json` (loaded by the composition root, sorted by file name):

```json
{
  "id": "conveyor_motor_fault",
  "title_en": "…", "title_de": "…", "description_en": "…", "description_de": "…",
  "steps": [
    {"when": {"var": "PLC01.parts_total", "op": ">=", "value": 3}, "set": {"CV01.motor_fault": true},
     "message_en": "…", "message_de": "…"},
    {"after": 20.0, "reset": ["CV01.motor_fault"]},
    {"after": 3.0, "pulse": {"PLC01.packml_command": 9}}
  ]
}
```

- Steps fire one after the other; each has exactly one trigger: `at` (s since scenario start), `after` (s since the
  previous step), `when` (`var` any FMI variable, `op` one of `>= > <= < == !=`, `value`).
- Actions: `set` (values), `pulse` (value for one master step, then 0 - like UNS pulse commands, for edge-triggered
  inputs), `reset` (list or `"all"`: back to the value before the scenario first changed it). A step without an action
  needs a `message_en` (instruction only).
- Only inputs and tunable parameters can be written (checked on start). Inputs that are wired in the layout are
  overwritten by the master every step - inject faults at unconnected inputs.

## ScenarioRunner (`godot/scenarios/`, depends on core only)

`FactoryRuntime.scenarios` (`ScenarioRunner`): `list(lang) -> [{id, title, description, steps}]`, `start(id)`,
`stop()` (restores every changed variable), `active`, `active_id`, `progress` (0..1), `step_index`, `elapsed`;
signals `started(id)`, `step_changed(index, step)`, `finished(id, completed)`. It is stepped from the physics loop after
the UNS commands and before the probes/master step. A scenario that runs to its end keeps its last values (all shipped
scenarios end with a reset). Dev argument `--vf-scenario=<id>` starts a scenario at launch.

## Shipped scenarios

| Id | Title (en / de) | Steps | Expected effect (checked by `tools/run_scenarios.sh`) |
|---|---|---|---|
| `missing_cap_burst` | Missing protective caps / Fehlende Schutzkappen | t=5 s missing-cap rate 0.6, +120 s reset | NOK parts rise (240 s run: 8 NOK of 18) |
| `dirty_color_sensor` | Dirty colour sensor / Verschmutzter Farbsensor | t=10 s contamination 0.2, +50 s 0.5, +90 s reset | ΔE rises, false rejects (10 NOK of 18) |
| `light_barrier_misalignment` | Misaligned light barrier / Dejustierte Lichtschranke | t=20 s LB02 0.3, +60 s 1.0, +20 s reset | false triggers (45 LB02 switchings for 22 parts, 9 NOK), alarm 302 (once the belt runs again in WAIT_PART), HELD, automatic resume |
| `conveyor_motor_fault` | Conveyor drive fault / Störung Förderbandantrieb | when 3 parts inspected: motor fault, +20 s reset, +3 s Clear, +2 s Reset | alarm 101, ABORTED, recovery to EXECUTE (16 parts in 240 s) |
| `robot_protective_stop` | Safety fence door opened / Schutzzauntür geöffnet | when robot program step ≥ 5: protective stop, +20 s reset | alarm 201, HELD, robot resumes its job, automatic resume |
| `gripper_wear` | Gripper finger wear (predictive maintenance) / Verschleiß der Greiferfinger (vorausschauende Instandhaltung) | t=5 s finger wear rate 4.5e-5 m/grip, when 6 grips: message, +90 s reset (normal wear, the fingers stay worn) | finger wear ≥ 0.4 mm without fault (240 s run: 0.60 mm after 13 grips, grip force 81 N, no regrip, line in EXECUTE). With the IT stack: maintenance order after ~5 grips (RUL lower bound ≈ 16 grips ≈ 4 min), advisory alarm 901, maintenance at the order boundary ([user guide](../user-guide.md#predictive-maintenance)) |

Run: `tools/run_scenarios.sh [id …]` (headless, 240 s simulated per scenario, `VF_SCENARIO_SECONDS` overrides;
`godot/tests/integration/scenario_run.gd` prints a report with alarm history and stack light state).
