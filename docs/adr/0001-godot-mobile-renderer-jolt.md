# ADR-0001: Godot 4.7, Mobile renderer, Jolt physics

- Status: accepted (renderer to be re-validated by the M1 performance baseline)
- Date: 2026-10-03

## Context
The factory must run on slower PCs (NFR-01) and stay XR-capable (NFR-02). Godot 4.7 offers three renderers:
Forward+ (desktop high-end), Mobile (Vulkan/Metal/D3D12, single-pass, cheap; used for standalone XR) and
Compatibility (OpenGL 3.3/ES 3, lowest requirements, fewer features).

## Decision
- **Mobile renderer** for all platforms, with low/medium/high quality presets.
- **Jolt Physics** (Godot's integrated Jolt) for rigid bodies (workpieces on the belt, dropping into KLTs).
- Physics tick 60 Hz. The co-simulation master steps with the physics tick.

## Consequences
+ One renderer for desktop and future standalone XR, and good performance on iGPUs.
− No SDFGI/volumetric fog. Lighting relies on baked lightmaps plus a few dynamic lights (enough for an industrial hall).
− Hardware without Vulkan/Metal/D3D12 needs the Compatibility renderer. It is tested in M1/M6; if it's needed, it
  becomes a per-platform override (`rendering_method.*`) instead of a project-wide switch.
