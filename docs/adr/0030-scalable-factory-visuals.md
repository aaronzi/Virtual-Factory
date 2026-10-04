# ADR-0030: Scalable factory visuals

- Status: accepted; supersedes ADR-0010's lighting values and single rendering budget; static lighting is baked
  since [ADR-0031](0031-baked-static-lighting.md)
- Date: 2026-10-04

## Context

The factory should look more realistic while remaining useful on ordinary laptops and, later, Quest 3.
The user accepts 30 FPS on a lower-tier laptop with a modest dedicated GPU; 60 FPS remains preferred.
The existing quality selector should control the whole visual workload. Desktop 30 FPS is not an XR target.

## Decision

Keep the Compatibility renderer and provide coherent Low, Medium (default) and High presets.
Use Blender-generated bevels, smooth cylinders, panel seams, vents, fasteners, cables, welded-wire fencing,
floor joints and industrial signs. Preserve animated object names and all collision/interaction geometry.

Bake local crevice shading into vertex colours and batch opaque finishes into paint, metal and rubber
materials. Preserve independently switched materials, labels and glass. A small import shader converts
linear glTF vertex colours for Compatibility's sRGB shading and adds filtered surface variation.
Use deterministic 512 px concrete/epoxy colour, roughness and normal maps, plus small contact-shadow cards.
No per-frame ambient-occlusion pass or texture downloads are required.

Low uses simpler imported mesh LODs, hides fine fence wires, disables floor texture sampling and real-time
shadows, and renders at 75% resolution without MSAA. Medium enables colour textures, shadows and 2× MSAA.
High uses finer LODs, floor roughness/normal maps, 4× MSAA, larger shadow maps and one box-projected
reflection probe capturing only the static hall. The probe and sky update once rather than every frame.
The same imported assets remain loaded at every preset; Low is not a texture-memory streaming solution.

Replace the universal 450-call ceiling with review budgets of 350/550/650 draw calls and
125k/250k/350k primitives for Low/Medium/High, including shadow/UI passes in the full-bin fixture.
These are regression budgets, not hardware performance guarantees. Record measured frame times and
validate representative camera positions; target-device measurements take precedence over the budget.

## Consequences

- Models, previews and AAS attachments are generated from the same sources; historical milestone captures
  remain historical. See [asset pipeline](../architecture/asset-pipeline.md).
- Quality switching is reversible during a running simulation, including textures and door details.
- The lighting remains an approximation of indoor illumination. Baked hall lightmaps remain a possible
  future improvement; moving equipment is absent from the static reflection capture.
- Laptop and Quest 3 performance remain unverified until tested on those devices. Start XR evaluation
  with Low, then tune eye resolution and anti-aliasing on the headset rather than using desktop defaults.
- Reproduction, measured results and limitations: [visual quality](../architecture/visual-quality.md).
