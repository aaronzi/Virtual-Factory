# ADR-0031: Baked lighting for static geometry, real-time shadows only for moving parts

- Status: accepted; implements the "baked hall lightmaps" left open by ADR-0010 and ADR-0030 (O7)
- Date: 2026-10-04

## Context

Real-time shadows were the weakest part of the image, most visibly on High. A single 2-split shadow map
covered the whole line and showed stair-stepped edges and only faint contact shading. Most of its casters
never move: hall floor, device bodies, stands, the fence, the cabinet and the robot pedestal.
Only the robot arm, the fence door and the workpieces move. The renderer stays Compatibility (ADR-0010). The
factory is assembled at runtime from the layout file, so the static geometry is not in a saved scene.

Godot 4.7 renders LightmapGI, including its shadowmask, in Compatibility. It bakes only with a
RenderingDevice renderer (Forward+/Mobile). It also exposes the bake only through the editor's
"Bake Lightmaps" action; `LightmapGI` has no scriptable `bake()`.

## Decision

- **What is baked:** static meshes of the hall floor and of all devices and props. The bake stores indirect
  light, sky occlusion and a shadowmask of the high-bay key light, with soft penumbrae (2° angular size).
  The rest of the hall shell is neither baked nor an occluder, as in ADR-0010.
- **What stays dynamic:** moving parts (`MovingParts`: robot links, conveyor drums, the door named by the
  layout's `moving_parts`) and small or transparent parts (lamps, LEDs, glass, labels). They are lit by the
  baked light probes and cast real-time shadows. Workpieces added later become dynamic automatically.
- **Shadowmask overlay:** baked static meshes stop casting real-time shadows. The key light's shadow map holds
  only moving casters and is combined with the shadowmask, so the robot shadow still lands on baked surfaces.
  Real-time acne on static surfaces disappears. Low keeps the light's shadows on with an empty caster mask,
  because Godot applies the shadowmask only to shadowed lights; it gets static shadows at no shadow-pass cost.
- **Light balance:** the key light uses 0.6 energy and full shadow opacity; the baked indirect light fills the
  shadows instead of an artificial opacity. The bake's ambient term uses the scene's ambient colour at
  0.14 energy, and the contact-shadow cards are hidden when a bake is applied. High also uses the finest
  real-time soft-shadow filter for the moving casters.
- **Reproducible bake:** `tools/bake_lighting.sh` builds the main scene headless exactly as at runtime. It
  mirrors the baked meshes by path into a bake scene, then runs the editor with `--rendering-method forward_plus`.
  A small editor plugin triggers the editor's own bake and quits.
  Imported GLBs get lightmap UV2 from the importer, and the committed `.unwrap_cache` files keep that UV2
  identical. Procedural meshes, here the merged conveyor parts, are unwrapped once and saved with the bake.
- **Stale-bake detection:** a manifest stores each baked mesh's placement, vertex count and UV2 hash. At
  runtime a mismatch keeps the previous real-time shadows and logs a warning. A GUT test fails until the bake
  is redone after layout or asset changes.
- **Texel density:** the hall floor is split into the epoxy production zone (`FloorZone`, 1.25 cm) and the
  surrounding slab (10 cm); equipment uses 2.5 cm. Settings: `godot/world/lighting/baked/<layout>/settings.json`.

## Alternatives considered

- **Higher-resolution real-time shadows only:** tighter cascades, more splits or PCSS. This would not create
  indirect light or contact occlusion. Compatibility has no PCSS, and every static caster stays in each split,
  so draw calls grow with quality.
- **Cycles bake in Blender:** high quality, but each asset is baked in isolation. Shadows between runtime-placed
  devices and the floor would need a Blender copy of the layout. The result would also need a hand-made
  `LightmapGIData` without light probes.
- **Static light bake mode:** direct light fully baked. Moving objects then cast no shadow onto lightmapped
  surfaces, leaving the robot "floating".
- **Baking the whole hall including walls and roof:** the roof blocks the key light, which stands in for the
  luminaire field. Godot's lightmapper ignores `cast_shadow = off` for occlusion.

## Consequences

- \+ Soft, stable, grounded static shadows on every preset, including Low, which previously had none. There
  are fewer draw calls and primitives, and no shadow acne on static surfaces.
- \+ Bake in about a minute on an Apple M4 Pro. Bake data is 6 MiB in Git (LFS): a 2048² lightmap
  (BPTC/ASTC, 4 MiB VRAM where supported) and an S3TC shadowmask.
- − Baking needs a desktop session: the editor window opens briefly. Headless CI cannot bake, but detects a
  stale bake. Layout or asset changes need a re-bake in the same change.
- − Static parts do not shadow moving ones; for example, KLT walls do not shadow workpieces. Moving parts
  receive only probe-based indirect light from the static scene.
- − macOS OpenGL has no BPTC. Godot decodes the lightmap to RGBA16F at load: 32 MiB VRAM plus a warning line.
  Startup is about 0.35 s longer from loading and the lightmap shader variants.
- − The fallback, a missing or stale bake, uses the brighter key light with real-time shadows from every caster.
- Procedure: [development.md](../development.md#baked-lighting); measurements:
  [visual quality](../architecture/visual-quality.md#baked-lighting).
