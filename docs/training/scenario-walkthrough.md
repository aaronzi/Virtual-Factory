# Scenario walkthrough: "Missing protective caps" with a production order

A 15-minute exercise that touches every layer of the Virtual Factory: shop floor (FMUs, PLC), UNS (MQTT), AAS
(BaSyx), MES workflow (BPMN) and the operator interfaces in the 3D scene. Verified on 2026-10-03 with the full stack.

**Setup**
```bash
docker compose -f infra/docker-compose.yml up -d
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```
Optional for the trainer: Operaton Cockpit (http://localhost:8092/operaton/app/cockpit/, demo/demo) on a second
screen, MQTT Explorer on `localhost:1883`.

## 1. Release a production order (MES)
Tasklist (http://localhost:8092/operaton/app/tasklist/) → *Start process* → **Production order (MES)**: quantity
24, manual KLT exchange off, reject rate limit 0.25.

What happens: the MES worker `line-start` invokes **LINE01 / LineControl / SetAutoExchange** and
**ExecutePackMLCommand** on the AAS; BaSyx delegates both to the ops gateway, which commands PLC01 over MQTT.
*Learning goal: IT systems command the line through its AAS, not through PLC addresses.*

## 2. Start the fault (trainer)
Esc → *Training scenarios* → **Missing protective caps** → *Start* (or `--vf-scenario=missing_cap_burst`). The cap
feeder of AC01 "jams": 60 % of the cylinders leave without the red cap for two minutes.
The same fault can be injected over MQTT (`.../ac01/cmd/defect_rate_missing_cap`), i.e. also by an agent.

## 3. Observe the shop floor
- The overlay / HMI show NOK rising; QS01 rejects caps that are not red (ΔE*ab > 25), the robot sorts them into
  KLT B.
- Click **QS01** → its AAS opens; OperationalData updates live (`delta_e`, `result_ok`) via BaSyx events.
- Click a cylinder in **KLT B** → its own AAS: QualityInspection *Fail / Rejected*, CapColour ΔE ≈ 60–80, the
  measured colour in CIELAB, CarbonFootprint, ExecutedProcesses OP10–OP90.
- Esc → *Show data flow*: orange packets for UNS events (device → gateway → broker → MES → BPMN), blue for device
  data going through the AIMC bridge into the AAS, green for workpiece AAS written by the MES.

## 4. The workflow reacts
After ≥ 10 parts with a reject rate above 25 % the order process holds the line (`line-command` → *Hold*), the
stack light turns amber, the HMI shows **HELD**, and the **MES terminal** next to the robot cell shows the task
**Investigate reject rate** (also in the Tasklist).

![MES terminal with the open task](../screenshots/m5-task-terminal.png)

## 5. Find the root cause
- Inspect **AC01** in the AAS inspector: OperationalData `last_cap_variant` = 0 (no cap) for the rejected parts.
- Compare with the AAS of a good part: OP70 "cap variant" says *red* for every part - the cell *believes* it
  fitted a cap; only the inspection detects the defect (why end-of-line inspection matters).
- Optional: Node-RED sandbox tab *Reject alarm* computes the same alarm from the UNS events.

## 6. Resolve
On the MES terminal enter *cause* ("cap feeder jammed") and *corrective action* ("cleared feeder, checked
sensor"), then **Complete task**. The order process unholds the line (`line-command` → *Unhold*) and continues;
the scenario resets the defect rate after two minutes. Cockpit shows the token moving back into the progress loop.

## Debrief questions
1. Why does the PLC sort by colour only, while the MES verdict also checks leak rate and stroke time?
2. Which AAS submodels changed for a rejected part, and which IDTA templates are they based on?
3. How would an AI agent detect and handle the same situation using only the AAS and the UNS?
