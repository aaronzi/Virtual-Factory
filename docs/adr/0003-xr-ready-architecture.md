# ADR-0003: XR-ready architecture without XR implementation

- Status: accepted
- Date: 2026-10-03

## Context

VR is a stated requirement for the future but should not be implemented now (user decision D1). There is no
OpenXR runtime on macOS, where development happens.

## Decision

Keep the system XR-ready through these rules:

1. 1 unit = 1 m, with real-world dimensions for all assets.
2. All player-related code depends only on the abstract `PlayerRig` (`core/interaction/player_rig.gd`).
   `DesktopRig` implements it now; a later `XRRig` (XROrigin3D + godot-xr-tools) implements the same interface.
3. Interactions go through a pointer abstraction (mouse ray now, controller ray later).
4. Core UI is world-space panels (SubViewport on a quad). Screen-space UI is only for desktop extras.
5. The renderer is XR-capable (Mobile, ADR-0001), with frame-time headroom budgeted for stereo rendering.
6. No hard camera cuts or forced camera motion in core flows.

## Consequences

- \+ VR becomes a module addition (an XRRig plus project settings), not a restructuring.
- − World-space UI needs slightly more work than plain 2D overlays.
