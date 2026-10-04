# ADR-0016: BPMN orchestration on MES level with Operaton

- Status: accepted
- Date: 2026-10-03

## Context

The MES coordinates slower, cross-system activities: creating and filling workpiece AAS along the process,
production orders, exceptions that need an operator. Hard-coded logic hides the process; a BPMN model makes it
visible and editable (bpmn.io), which is valuable for training. Real-time control (sorting decision, PackML state
machine) must stay in the PLC.

## Decision

- **Operaton 2.1.5** (Apache 2.0 fork of Camunda 7 CE, which reached end of life in 2025) as engine, container
  `bpmn` (port 8092: REST, Cockpit, Tasklist; local user demo/demo; in-memory H2 = ephemeral like the AAS server).
  CIB seven was the alternative; Operaton has monthly releases and arm64 images. Camunda 8 was ruled out because of
  its self-managed licence; Imixs-Workflow (Open-BPMN) targets human workflow rather than service orchestration.
- Models in `bpmn/` (BPMN 2.0 with diagram interchange, editable with bpmn.io / Camunda Modeler), deployed by the
  MES at start-up:
  - `WorkpieceLifecycle`: one instance per part (business key = serial), message events correlated from the UNS
    events, external tasks that write the workpiece AAS, timeouts for lost parts, user task for mis-sorted parts.
    It is the executable procedure of the master recipe (`ManufacturingRecipe/Procedure/ProcedureModel`, steps
    reference their BPMN task in `ExecutionElement`).
  - `ProductionOrder`: starts the line via the AAS (LineControl operations, ADR-0017), polls progress from the AAS,
    holds the line and creates an operator task when the reject rate exceeds a limit, event sub-process for full
    KLTs (manual exchange in the task list on request).
- All service tasks are **external tasks** handled by Python workers in the MES (no Java code in the engine).

## Consequences

- \+ The process is visible live in Cockpit (token positions, incidents) and the operator tasks appear in Tasklist.
- \+ Clear split: PLC = real-time control, BPMN = orchestration of IT activities and human tasks.
- − One more container (~400 MB image, JVM). Message correlation needs retries because UNS events can arrive before
  the instance waits for them (handled in the MES).
