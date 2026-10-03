# Device: stack_light

Signal tower (LED segments green/amber/red from bottom to top above a buzzer module, on a short pole with a mounting
base), mounted on top of the line control cabinet. 24 V DC, driven directly by PLC outputs.

| Part | File |
|---|---|
| Behaviour (FMU) | `model/stack_light_model.gd` + `model/modelDescription.xml` |
| View | `view/stack_light_view.gd` + `view/stack_light.glb` (from `blender/scripts/build_stack_light.py`): the segments `LampGreen`, `LampAmber`, `LampRed` glow while lit (`Indicator`) |

The device origin is the centre of the mounting base (bottom face). Overall height 0.46 m.

Key variables: inputs `green`, `amber`, `red`, `buzzer`; parameters `lamp_power`, `buzzer_power`, `standby_power`;
outputs `green_on`, `amber_on`, `red_on`, `buzzer_on`, `power`, `energy`, `operating_hours`.
Meaning of the colours is defined by the PLC (`light_green/amber/red`, `horn`, see docs/interfaces/scenarios.md).
The buzzer is not audible (no audio in the simulation); `buzzer_on` is published like every output.
