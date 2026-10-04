# Device: klt_container

VDA small load carrier (KLT 6428, 600 × 400 × 280 mm) on a stand: A = good parts (blue), B = rejects (red).

| Part | File |
|---|---|
| Behaviour (FMU) | `model/klt_container_model.gd` + `model/modelDescription.xml` |
| Physical stimulus | `probes/fill_probe.gd`: Area3D over the inner volume counts resting items |
| View + actuator | `view/klt_greybox_view.gd`: box and stand. On an exchange event the items inside are retired. Provides palletizing teach markers `SlotOrigin`, `SlotRowEnd`, `SlotColEnd` |
| Geometry | `model/klt_geometry.gd` |

Geometry options: `color` (html), `stand_height` (0.55 m), `pick_height` (robot grip height above the part bottom,
0.15 m), `slot_span_x` (0.2), `slot_span_z` (0.36).
