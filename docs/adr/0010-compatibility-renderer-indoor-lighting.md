# ADR-0010: Compatibility renderer as default; indoor lighting without baking

- Status: accepted (supersedes the renderer choice of ADR-0001; Jolt part of ADR-0001 still valid)
- Date: 2026-10-03

## Context

User decision at the M1 checkpoint: slow PCs come first, mobile platforms are not a target, and standalone VR may
come later. M1 measurements: Compatibility was about 1.75× faster than Mobile on the same scene.
The hall gets a roof, so the scene must stay well lit without daylight.

## Decision

- `rendering_method = gl_compatibility` (OpenGL 3.3 / ES 3.0) for all platforms. It is also the usual choice for
  standalone XR in Godot.
- Lighting without baked lightmaps (no editor bake step, works headless/CI):
  - Environment ambient colour (0.84, 0.87, 0.92) at energy 0.42.
  - **High-bay key light**: a steep directional light (≈58°), energy 0.6, shadows with 2 cascades over 20 m.
  - **Fill light**: an opposite directional light without shadows, energy 0.3.
  - The hall shell (roof, walls, structure) does not cast shadows, so the key light reaches the floor through the
    roof, standing in for the many high-bay luminaires. The emissive luminaire meshes are only visual.
- Materials are authored in sRGB in Blender and converted to linear (`vf_lib.material`). Paints are dielectric
  (metallic 0) to avoid specular hotspots in the Compatibility renderer.
- Draw-call measures:
  - Static batching of repeated parts (`MeshMerger`, used for the conveyor).
  - The product has 4 body materials.
  - Tiny devices (light barriers) do not cast shadows.

## Measurements (1920×1080, Apple M4 Pro; FPS capped by display refresh)

| State | Draw calls | Primitives (incl. shadow pass) |
|---|---|---|
| Before optimisation, KLTs filling | 694 | 108 k |
| After (2 cascades, hall without shadows, merged conveyor, 4-material product) | **370** | **55 k** |

NFR-01 budget updated: **≤ 450 draw calls and ≤ 250 k primitives, both including the shadow pass, with full KLTs.**
The original ≤ 300 did not account for the shadow pass.

## Consequences

- \+ Runs on old iGPUs, and the same renderer can serve standalone XR.
- − No SSAO/SDFGI/volumetrics, so contact shadows come only from the directional shadow map.
- − Lighting is "studio-like" rather than physically accurate per luminaire. Baked LightmapGI (supported for rendering
  in Compatibility) is an optional future improvement (O7).
