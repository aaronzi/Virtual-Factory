# Runtime view: life cycle of one part (M1, OT layer only)

Times are for the default layout (takt 12 s, belt 0.25 m/s). The IT side (MQTT, MES, AAS) is added in M4.

```mermaid
sequenceDiagram
  autonumber
  participant AC as AC01 assembly cell
  participant CV as CV01 conveyor
  participant LB1 as LB01
  participant LB2 as LB02
  participant QS as QS01 QA station
  participant PLC as PLC01 SortingLine
  participant RB as RB01 UR5e
  participant K as KLT A/B
  PLC->>AC: enable, infeed_free
  AC-->>AC: assemble (takt 12 s)
  AC->>PLC: release_count++, last_serial
  Note over AC,CV: ItemSpawner spawns the workpiece at the outlet
  PLC->>PLC: FIFO.push(serial), infeed occupied
  LB1->>PLC: signal ↑↓ (part passes) -> infeed free
  CV-->>LB2: part arrives (~10 s)
  LB2->>PLC: signal ↑
  PLC->>CV: run = false after stop delay (0.165 s)
  PLC->>QS: trigger (after settle 0.35 s)
  QS->>PLC: result_valid, result_ok (ΔE76 vs. taught red)
  PLC->>PLC: serial_at_qs = FIFO.pop(), counters
  PLC->>RB: job_start, place_target (1 = A, 2 = B), place_slot
  RB-->>RB: movej approach, movel down, grip
  RB->>PLC: part_clear (lifted)
  PLC->>CV: run = true (next part)
  RB-->>K: movej to slot, movel down, release, retreat, home
  RB->>PLC: job_done
  PLC->>RB: job_start = false (acknowledge)
  K->>PLC: fill_count (presence sensor)
  Note over PLC,K: KLT full: PackML SUSPEND until exchanged (auto after 4 s or by operator)
```

Per physics frame (`factory/factory_runtime.gd`):

1. every device's **probes** sample the world (beam raycasts, colour ray, grip/fill overlaps) → model inputs
2. `CoSimMaster.step(1/60 s)`: connections copied, `do_step` for each device, then the PLC (10 ms scans)
3. every device's **views** apply outputs (belt velocity, joint transforms, lamps, spawning, grasping)
