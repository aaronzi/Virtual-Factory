# Factory visual review

Current captures (2026-10-04, Compatibility renderer):

| Image | Content |
|---|---|
| [High](factory-high.png) | High preset, training UI |
| [Medium](factory-medium.png) | Default preset, same camera |
| [Low](factory-low.png) | Simplified fallback, same camera |
| [Line](factory-line.png) | UI-free line view; LINE01 AAS thumbnail/document preview |
| [Robot](factory-robot.png) | Close view of robot, enclosure and finishes |
| [Inspector](factory-inspector.png) | Robot AAS and refreshed thumbnail |
| [Data flow](factory-dataflow.png) | Current geometry with OT/IT overlay |
| [Quality menu](factory-quality-menu.png) | Quality selector and preset explanation |
| [Asset previews](assets/) | Blender studio renders used by AAS thumbnails and Models3D |
| [Baked lighting: line](m10-baked-line-high.png), [robot](m10-baked-robot-high.png), [cell](m10-baked-cell-high.png), [fence](m10-baked-fence-high.png) | High before/after [ADR-0031](../adr/0031-baked-static-lighting.md), eye height 2–4 m from the line |
| [Baked lighting: Medium](m10-baked-line-medium.png), [Low](m10-baked-fence-low.png) | Same comparison on Medium and Low (Low previously had no shadows) |

The `factory-*` captures predate the baked lighting; the `m10-baked-*` images show the current lighting.

![High](factory-high.png)
![Low](factory-low.png)
![Baked lighting, fence on High](m10-baked-fence-high.png)

Regenerate assets/previews through Blender MCP with `blender/scripts/build_all.py`, import into Godot,
then run `tools/update_visual_screenshots.sh`. Screenshots disable outbound simulation links and retention;
the local backend supplies read-only inspector/data-flow content. Rebuild AASX packages with
`uv run -m provisioner build` and validate with `uv run tools/check_aasx.py`.

For an existing local AAS environment, `uv run tools/refresh_aas_visuals.py` lists the planned visual-only
updates; add `--apply` to update thumbnails, matching PNG/GLB File attachments and Models3D version/date
metadata, with byte-for-byte verification. It does not re-provision device state or existing item passports.
Refresh the live visuals before taking inspector screenshots. Restart any client caching old thumbnails.

`m0-*` through `m9-*`, milestone GIFs and scenario walkthrough captures are historical evidence of those
milestones/workflows. Their visual appearance is not the current preset. The Blender demo source is refreshed;
the old milestone GIF remains archived. See [visual quality](../architecture/visual-quality.md) for settings,
reproduction, measured workload and target-hardware limitations.
