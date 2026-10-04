# ADR-0018: In-world training UI - world-space panels, passive views, live AAS via events

- Status: accepted
- Date: 2026-10-03

## Context

M5 adds the operator and learner interface: an AAS inspector for every asset (including each workpiece), the line
HMI, the MES terminal with the BPMN user tasks (M4 review: tasks in the Tasklist *and* in the scene), training
scenarios, a demo tour and a data-flow visualisation. The UI must stay XR-ready (ADR-0003) and respect the module
rules (ADR-0006: `ui` depends only on `core`).

## Decision

- **World-space panels** (`ui/world_panel`): a Control in a SubViewport on a quad; the `PointerRouter` raycasts the
  `PlayerRig` pointer each frame and forwards hover/press/release to `Interactable`s (`core/interaction`), which
  turn hits into viewport mouse events. Desktop mouse and a later XR controller ray use the same path. Physics
  layers: 10 = UI panels, 11 = selection volumes (ignored by the UI pointer).
- **Passive views, controllers in the composition root**: views in `ui/` only render pushed data and emit user
  intentions; controllers in `factory/` (inspector, HMI, tasks, menu, data flow) connect them with `connectivity`
  clients and the co-simulation. This keeps `ui -> core` only.
- **AAS inspector**: assets are picked through selection volumes (devices, tagged props) or the workpiece body
  (serial → `WP_` tag). Live values: BaSyx MQTT CloudEvents (`vf/basyx/#`) mark the visible submodel stale and it
  is re-fetched (debounced 0.4 s) - events, then fetch, as decided in the M4 review.
- **HMI** writes PLC inputs through `LocalCommands` (fieldbus path of a real HMI, pulse semantics like the UNS
  gateway), not through MQTT or the AAS.
- **BPMN tasks** are polled from Operaton every 2 s (no push channel); the KLT stations offer "exchange done" when
  an *Exchange KLT* task exists for them.
- Desktop extras (F1 menu, captions) are screen-space CanvasLayers; everything an operator needs in training is in
  world space.
- i18n: Godot CSV translations (`ui/i18n/ui.csv`); static texts hold translation keys so a language switch updates
  them live.

## Consequences

- \+ The same panels work in VR later; the UI module stays independent of the backend clients and of devices.
- \+ Learners see the real data path (data-flow view is driven by real UNS and BaSyx events).
- − SubViewport panels cost one render target each (4 panels, updated only when visible).
- − The inspector depends on the backend; without it the panel shows "no AAS found" while the factory keeps running.
