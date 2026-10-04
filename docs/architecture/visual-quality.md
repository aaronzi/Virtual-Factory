# Visual quality and performance

The F1 menu switches complete presets immediately. Medium is the default, including when no developer
arguments are supplied. `--vf-quality=0|1|2` selects the same presets at startup.
Decisions: [ADR-0030](../adr/0030-scalable-factory-visuals.md), baked lighting
[ADR-0031](../adr/0031-baked-static-lighting.md).

| Setting | Low | Medium | High |
|---|---|---|---|
| Purpose | Broad desktop compatibility | Everyday laptop | Best available visual detail |
| Internal resolution | 75% per axis | 100% | 100% |
| MSAA | Off | 2× | 4× |
| Mesh LOD pixel threshold | 6 (coarser) | 2 | 0.5 (finer) |
| Fine fence-wire geometry | Hidden | Visible | Visible |
| Concrete/epoxy colour textures | Flat fallback colours | 512 px, mipmaps | 512 px, mipmaps |
| Concrete/epoxy roughness and normal maps | Off | Off | On |
| Filtered coating/metal variation | Off | Reduced | Full |
| Baked lightmap and static shadows (shadowmask) | On | On | On |
| Real-time shadows (moving parts only) / atlas | Off (no casters) | 2048 px, soft low | 4096 px, soft high |
| Static hall reflection probe | Off | Off | On, box projected, update once |
| Baked local vertex shading | On | On | On |
| Contact-shadow cards | Hidden (baked) | Hidden (baked) | Hidden (baked) |
| Draw-call review budget | 350 | 550 | 650 |
| Primitive review budget | 125,000 | 250,000 | 350,000 |

LOD uses Godot's imported mesh LODs, where available; it does not swap in separately authored full models.
Higher thresholds simplify sooner. Fine wire meshes retain their Door parent so they follow the hinge.
Panels, nameplates, QR codes, lamps, product variants, physics and picking volumes work at every preset.
Low removes texture sampling but the original resources remain resident for instant restoration; it does
not guarantee lower texture memory. New surface maps are 512×512, contact cards 64×64. GLB file sizes are
storage sizes, not measurements of GPU memory.

## Measured rendering fixture

`tools/benchmark_visuals.sh --vf-inspect=RB01` renders the actual factory at 1920×1080, with two full KLTs
(24 cylinders), three belt cylinders, training panels and the robot inspector. It exercises preset changes
before measurement. Five seconds warm-up, ten seconds sampling, vsync off, Godot 4.7.2 Compatibility,
Apple M4 Pro, 2026-10-04. Max draw calls/primitives include UI and shadow passes. Logs are written to
`build/visual-review/quality-{0,1,2}.log`.

| Preset | Max draw calls | Max primitives | Mean FPS | Mean ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|
| Low | 308 | 39,719 | 290.2 | 3.45 | 5.21 | 8.54 |
| Medium | 482 | 76,029 | 224.2 | 4.46 | 5.91 | 7.21 |
| High | 482 | 98,679 | 236.0 | 4.24 | 6.43 | 6.86 |

Frame times are wall-clock frame intervals (p95/p99), not isolated GPU timings. This fixture freezes the
simulation and disables UNS/backplane/event connections and persistence. It measures rendering, not the
full live-service workload. Startup shader compilation and reflection capture are outside the sample.
Additional camera checks (same 27-part fixture):

| View | Low calls / primitives | Medium calls / primitives | High calls / primitives |
|---|---:|---:|---:|
| Robot close-up | 293 / 37,917 | 527 / 103,237 | 527 / 111,989 |
| Wide + data-flow overlay | 347 / 32,717 | 530 / 58,801 | 530 / 78,295 |

Reproduce with `--vf-camera=1.4,1.7,1.2,0.25,0.6,-0.55` or
`--vf-dataflow --vf-camera=8,6,9,-1,1,0` after the benchmark command. These samples fit all three budgets;
Low has little remaining draw-call margin in the wide overlay view. The script fails when a draw-call
or primitive budget is exceeded. Save logs before changing views, as each invocation replaces them.

Numbers vary with scheduling, camera and inspector content; a faster High sample does not mean High is
cheaper. Budget checks must also cover wide and close camera positions and data-flow overlays.

The previous live default-camera baseline was 350 calls / 46,998 primitives, but had different occupancy;
it is not an apples-to-apples speed comparison. Batching limits the cost of the added geometry without
claiming a measured before/after FPS improvement.

## Baked lighting

Static geometry uses a LightmapGI bake with a key-light shadowmask
([ADR-0031](../adr/0031-baked-static-lighting.md); procedure in [development.md](../development.md#baked-lighting)).
The real-time shadow map holds only moving parts. Measured on 2026-10-04 with the frozen fixture above
(`--vf-inspect=RB01`, 1920×1080, Apple M4 Pro), interleaved with a checkout of the previous commit.
Values are steady-state per-frame medians; the maxima are 68 calls higher in frames that re-render a
world panel.

| View / preset | Draw calls before → after | Primitives before → after |
|---|---:|---:|
| Default camera, Low | 240 → 235 | 37,896 → 37,612 |
| Default camera, Medium | 414 → 373 | 74,206 → 63,730 |
| Default camera, High | 414 → 373 | 96,856 → 85,932 |
| Robot close-up, Low | 225 → 220 | 36,094 → 36,066 |
| Robot close-up, Medium | 459 → 394 | 101,414 → 80,306 |
| Robot close-up, High | 565 → 394 | 114,167 → 89,066 |

Mean frame times of `tools/benchmark_visuals.sh` (two interleaved runs each, before → after): Low 3.24–3.51 →
3.79–3.84 ms, Medium 3.99–4.78 → 4.04–4.15 ms, High 3.82–3.97 → 3.96–4.04 ms. Medium and High are unchanged
within run-to-run noise. Low pays about 0.3 ms for the lightmap and the shadowmask lookup; Low previously had
no shadows at all. Its real-time range is 0.1 m with no casters, so no shadow-map lookups are made.
Startup is about 0.35 s longer (2.7 → 3.05 s to a running scene, lightmap shader variants and data).
Godot reports 8.6 MiB more video memory on High. On macOS the BPTC lightmap is decoded to RGBA16F at load.

Some samples ran at a 6.90 ms (145 Hz) cap when macOS throttled the window; those were discarded. A slow pan
on High counted the frame-to-frame luminance alternations of the floor band (`--write-movie`,
`--vf-tour=<path>.json`). The result was 647 per frame with the bake, against 703 with real-time static
shadows, so there is no flicker regression. Static surfaces no longer receive real-time shadows, so they
cannot show shadow acne.

## Acceptance on target hardware

Desktop goal: at least 30 FPS (33.3 ms/frame) at 1080p output on a lower-tier laptop with a modest dedicated
GPU using a suitable preset; 60 FPS (16.7 ms/frame) preferred. Low is the fallback for weaker machines.
This has **not** been validated on the target laptop. For acceptance, record the GPU/driver, power mode,
resolution and preset, run a full production cycle with services and full bins, visit every camera/UI view,
and report sustained frame times, p95/p99, draw calls, memory and thermal behaviour.

Quest 3 has a separate acceptance gate: at least the headset's selected refresh rate (72 Hz minimum,
13.9 ms/frame at 72 Hz), stereo eye resolution and a sustained thermal run on the headset. Desktop 30 FPS
is insufficient for that gate. Low is only a starting point; test 2× MSAA for wire/text stability, actual
OpenXR multiview and eye resolution. See [XR readiness](xr-readiness.md). No Quest performance claim is made.

## Rebuild and review

1. Run `blender/scripts/build_all.py` through Blender MCP; it regenerates `.blend`, `.glb` and asset previews.
2. Run Godot `--headless --path godot --import`, then `uv run tools/inspect_visual_assets.py`.
3. Run `tools/bake_lighting.sh` if static assets or the layout changed
   ([baked lighting](../development.md#baked-lighting)); the GUT suite fails on a stale bake.
4. Run `tools/run_godot_tests.sh`, `tools/run_line_simulation.sh`, and the render benchmark above.
5. Run `tools/update_visual_screenshots.sh` (local backend needed for inspector/data-flow content).
6. Run `uv run -m provisioner build`, then `uv run tools/check_aasx.py`. Existing running AAS environments
   require their visual attachments to be refreshed separately; see [screenshot inventory](../screenshots/README.md).

The regression tests inspect real imported assets and check High → Low → High restoration, door hierarchy,
robot joint names and vertex-colour batching. See `godot/world/tests/test_quality_settings.gd`.

References: Godot [mesh LOD threshold](https://docs.godotengine.org/en/stable/classes/class_viewport.html#class-viewport-property-mesh-lod-threshold),
[vertex colour conversion](https://docs.godotengine.org/en/stable/classes/class_basematerial3d.html#class-basematerial3d-property-vertex-color-is-srgb),
[reflection probe](https://docs.godotengine.org/en/stable/classes/class_reflectionprobe.html),
[LightmapGI](https://docs.godotengine.org/en/stable/classes/class_lightmapgi.html),
Meta [mobile performance](https://developers.meta.com/vr/documentation/unity/po-perf-opt-mobile/).
