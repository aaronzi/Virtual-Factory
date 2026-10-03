# XR readiness review (M6)

Decision: VR is not implemented now, but the architecture must allow adding it without restructuring
([ADR-0003](../adr/0003-xr-ready-architecture.md), D1). This review checks the criteria on 2026-10-03.

| Criterion | Status | Evidence |
|---|---|---|
| 1 unit = 1 m, real-scale assets | ✔ | Layout and Blender scripts in metres; UR5e with real DH parameters |
| Player abstraction | ✔ | All UI/gameplay code talks to `PlayerRig` (`core/interaction/player_rig.gd`): pointer ray, press/release, view camera, teleport |
| XR rig exists and compiles | ✔ | `player/xr_rig.gd`: XROrigin3D + XRCamera3D + two XRController3D; right ray = pointer, trigger = press, smooth move + snap turn; GUT test `player/tests/test_xr_rig.gd` |
| Graceful fallback | ✔ | `--vf-xr` tries OpenXR; without a runtime the desktop rig stays (verified on macOS) |
| World-space UI | ✔ | Inspector, HMI, MES terminal are `WorldPanel`s driven by the `PointerRouter` (ADR-0018); only the F1 menu and captions are desktop extras |
| Interaction without mouse specifics | ✔ | Selection volumes / Interactables use the rig's ray; no screen-space picking in training features |
| Renderer supports XR | ✔ | Compatibility renderer (OpenGL) supports OpenXR in Godot 4.7; draw-call budget leaves room for stereo only with the Low/Medium presets (see below) |
| Comfort | ◐ | Snap turn and smooth locomotion implemented; vignette, teleport locomotion and seated mode not yet |
| Performance in stereo | ◐ | Desktop frame ≈ 4 ms on the dev machine; stereo roughly doubles the draw calls (449 → ~900), so the Low preset (no shadows) is required for standalone headsets |
| Text legibility | ◐ | Panels at 1000–1100 px/m and 17–30 px fonts are readable at 0.6–1.2 m on desktop; to be checked in a headset |

## Enabling VR (when a headset is available)
1. Project settings: `xr/openxr/enabled = true`, `xr/shaders/enabled = true` (Windows/Linux with an OpenXR
   runtime such as SteamVR or the Meta runtime).
2. Start with `--vf-xr --vf-quality=0`.
3. Add an XR export preset (Android for standalone headsets needs the OpenXR vendors plugin).

## Open points
- Scrolling uses `PlayerRig.pointer_scrolled` (wheel steps): desktop mouse wheel/trackpad, XR right thumbstick
  up/down (the left thumbstick moves, right left/right snap-turns); the PointerRouter forwards it to the panel
  under the ray (O32).
- The F1 menu is screen-space: an XR menu panel on the left controller is needed for scenario/tour control.
- Not tested on a headset (no OpenXR runtime on macOS) - R10.
