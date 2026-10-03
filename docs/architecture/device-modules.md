# Concept: device modules

A device type is a self-contained folder `godot/devices/<type>/` (isolated from other device types,
checked by `tools/arch_check.py`). It plugs into the factory only via its FMI variables and three
`core` contracts.

| Part | Base class (core) | Responsibility | Scene tree access |
|---|---|---|---|
| Model | `Fmi3CoSimulation` | Behaviour (pure logic) + `modelDescription.xml` | none |
| Probe | `DeviceProbe` | Physical world → model inputs (raycasts, overlaps, surface colour) | read |
| View | `DeviceView` | Model outputs → 3D (transforms, materials, belt velocity, spawning, grasping) | write |
| Root | `DeviceNode` | Owns the model, collects probes/views, `world_to_device_frame()`, markers | — |

Rules:
- Scene file `devices/<type>/<type>.tscn` (naming convention used by `FactoryBuilder`).
- Layout options for views/probes come from `DeviceNode.geometry`; model parameters come from the layout's
  `parameters`.
- Physical items are only known as `TrackedItem` (core). Spawning uses the injected `ItemFactory`
  (`DeviceNode.services["item_factory"]`, a small scoped service registry set by the composition root).
- Teach points are `Marker3D` nodes (e.g. `PickPoint`, `SlotOrigin`); the layout's `teach` section copies
  their positions into other devices' parameters, expressed in the target device's frame.
- Views are greybox (primitive) views in M1; Blender views replace them in M2 without touching models.

Adding a device type = new folder + layout entry (+ connections). Nothing else changes.
