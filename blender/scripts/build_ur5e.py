"""UR5e robot arm with 2-finger gripper and pedestal (recognisable proportions, no logos).

Origin = robot base frame (pedestal top), Z up, same frame as the kinematics (ur_kinematics.gd).
Hierarchy (all empties lie exactly on the standard-DH frames at the zero pose):
  Base (static: base housing, mounting plate) + Pedestal
  J1 (frame 0, rotates about local Z) -> L1 (frame 1) -> J2 -> L2 -> J3 -> L3 -> J4 -> L4 -> J5 -> L5
  -> J6 -> L6 (flange frame) -> Gripper, FingerA, FingerB (move along local X), TCP (empty, 0.16 m)
In Godot the glTF import maps local Z -> local Y, so joint i is driven by J<i>.basis = Basis(UP, q_i).
Link meshes follow the UR5e layout at the zero pose (arm stretched along -X, joint offsets along -Y:
shoulder +0.138, elbow -0.131, wrist +0.127 -> d4 = 0.1333).
Export: godot/devices/ur5e/view/ur5e.glb
"""

import importlib
import math
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

importlib.reload(L)
L.reset_scene()

D1, A2, A3, D4, D5, D6 = 0.1625, -0.425, -0.3922, 0.1333, 0.0997, 0.0996
D = [D1, 0, 0, D4, D5, D6]
A = [0, A2, A3, 0, 0, 0]
ALPHA = [math.pi / 2, 0, 0, math.pi / 2, -math.pi / 2, 0]
TOOL = 0.16
grey = L.material("robot_grey")
cap = L.material("robot_cap")
dark = L.material("plastic_dark")
X_EL, X_WR = A2, A2 + A3          # elbow and wrist x at the zero pose
Y_UA, Y_FA = -0.138, -0.007       # upper arm / forearm centre planes
Z_SH = D1


def dh(i: int) -> Matrix:
    a, d, al = A[i], D[i], ALPHA[i]
    return (Matrix.Translation((0, 0, d)) @ Matrix.Translation((a, 0, 0)) @ Matrix.Rotation(al, 4, "X"))


def housing(name, center, axis, r, length, lid_side=0, segments=24):
    """Joint housing cylinder with an optional blue lid at the +/- end along its axis."""
    parts = [L.cylinder(name, r, length, center, grey, axis=axis, segments=segments, bevel=0.004)]
    if lid_side:
        off = Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]) * (lid_side * (length / 2 + 0.003))
        parts.append(L.cylinder(f"{name}Lid", r * 0.92, 0.008, Vector(center) + off, cap, axis=axis,
                                segments=segments, bevel=0.002))
    return parts


def tube(name, x0, x1, y, z, r):
    return L.cylinder(name, r, abs(x1 - x0), ((x0 + x1) / 2, y, z), grey, axis="X", segments=20)


links = {
    0: [L.cylinder("BaseHousing", 0.075, 0.09, (0, 0, 0.045), grey, segments=28, bevel=0.004),
        L.cylinder("BaseRing", 0.077, 0.012, (0, 0, 0.006), dark, segments=28),
        L.cylinder("BaseBand", 0.0765, 0.01, (0, 0, 0.085), cap, segments=28)],
    1: housing("Shoulder", (0, 0, 0.13), "Z", 0.062, 0.08, 0, 28)
       + housing("J2Housing", (0, -0.065, Z_SH), "Y", 0.062, 0.13, +1, 28),
    2: housing("UpperArmRoot", (0, Y_UA, Z_SH), "Y", 0.058, 0.08, -1, 28)
       + [tube("UpperArm", -0.03, X_EL + 0.03, Y_UA, Z_SH, 0.045)]
       + housing("UpperArmEnd", (X_EL, Y_UA, Z_SH), "Y", 0.055, 0.08, -1, 28)
       + housing("ElbowMotor", (X_EL, -0.0725, Z_SH), "Y", 0.05, 0.06, 0, 24),
    3: housing("ForearmRoot", (X_EL, Y_FA, Z_SH), "Y", 0.048, 0.07, +1, 24)
       + [tube("Forearm", X_EL - 0.03, X_WR + 0.03, Y_FA, Z_SH, 0.038)]
       + housing("Wrist1", (X_WR, -0.04, Z_SH), "Y", 0.045, 0.095, +1, 24),
    4: housing("Wrist2", (X_WR, -D4, Z_SH - 0.045), "Z", 0.045, 0.1, +1, 24),
    5: housing("Wrist3", (X_WR, -D4 - 0.05, Z_SH - D5), "Y", 0.045, 0.09, 0, 24),
    6: [L.cylinder("ToolFlange", 0.0315, 0.012, (X_WR, -D4 - D6 + 0.006, Z_SH - D5), dark, axis="Y",
                   segments=20)],
}


def _attach(obj, parent_obj, local=Matrix.Identity(4)):
    obj.parent = parent_obj
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = local


def build_hierarchy():
    """J/L empties with explicit local DH matrices; link meshes re-expressed in their link frame."""
    base = L.empty("Base")
    _attach(L.join(links[0], "BaseLink"), base)
    parent, frame = base, Matrix.Identity(4)
    joints = {}
    for i in range(6):
        j = L.empty(f"J{i + 1}")
        _attach(j, parent)                      # joint i sits on frame i-1, rotates about local Z
        l_ = L.empty(f"L{i + 1}")
        _attach(l_, j, dh(i))                   # frame i = frame i-1 · Tz(d) Tx(a) Rx(alpha)
        frame = frame @ dh(i)
        mesh = L.join(links[i + 1], f"Link{i + 1}")
        mesh.data.transform(frame.inverted())   # world (zero pose) -> link frame coordinates
        _attach(mesh, l_)
        joints[i + 1] = (j, l_)
        parent = l_
    return base, joints


def build_gripper(flange_empty):
    """2-finger parallel gripper in flange coordinates (tool Z out of the flange, fingers along X)."""
    body = L.join([
        L.cylinder("Coupling", 0.04, 0.012, (0, 0, 0.006), dark, axis="Z", segments=20),
        L.box("GripBody", (0.1, 0.06, 0.075), (0, 0, 0.05), L.material("plastic_black"), bevel=0.008),
        L.box("Rail", (0.11, 0.02, 0.012), (0, 0, 0.093), L.material("steel_zinc")),
        L.cylinder("Cable", 0.005, 0.06, (0.06, 0.02, 0.04), L.material("plastic_black"), axis="X", segments=8),
    ], "Gripper")
    _attach(body, flange_empty)
    fingers = []
    for name, sx in (("FingerA", 1), ("FingerB", -1)):
        finger = L.join([
            L.box(f"{name}Body", (0.012, 0.024, 0.07), (0, 0, 0), L.material("alu_anodised"), bevel=0.002),
            L.box(f"{name}Pad", (0.004, 0.02, 0.03), (-sx * 0.0075, 0, 0.012), L.material("rubber")),
        ], name)
        _attach(finger, flange_empty, Matrix.Translation((sx * 0.0485, 0, TOOL - 0.01)))
        fingers.append(finger)
    tcp = L.empty("TCP")
    _attach(tcp, flange_empty, Matrix.Translation((0, 0, TOOL)))
    return body, fingers


def pedestal():
    paint = L.material("paint_anthracite")
    parts = [L.box("Column", (0.2, 0.2, 0.7), (0, 0, -0.38), paint, bevel=0.006),
             L.box("TopPlate", (0.26, 0.26, 0.02), (0, 0, -0.01), L.material("steel_zinc"), bevel=0.003),
             L.box("FloorPlate", (0.45, 0.45, 0.025), (0, 0, -0.7375), paint, bevel=0.004)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(L.cylinder("Anchor", 0.012, 0.02, (sx * 0.18, sy * 0.18, -0.715), L.material("steel_zinc"),
                                    segments=6))
            parts.append(L.box("Gusset", (0.012, 0.1, 0.1) if sx else (0.1, 0.012, 0.1),
                               (sx * 0.106, 0, -0.68) if sy > 0 else (0, sx * 0.106, -0.68), paint))
    parts.append(L.decal("Warning", "warning_robot.png", 0.09, 0.08, (0, -0.1005, -0.3), (90, 0, 0)))
    return L.join(parts, "Pedestal")


base, joints = build_hierarchy()
gripper, fingers = build_gripper(joints[6][1])
_attach(pedestal(), base)

L.export_glb(L.REPO / "godot" / "devices" / "ur5e" / "view" / "ur5e.glb")
L.save_blend("ur5e")
tris = L.triangle_count()

import bpy  # noqa: E402

# review pose (typical working pose) for the render, then back to zero
POSE = [0.6, -1.25, 1.55, -1.87, -1.57, 0.3]
for i, q in enumerate(POSE):
    joints[i + 1][0].rotation_euler.z = q
bpy.context.view_layer.update()
L.render_preview("ur5e", target=(0, 0, 0.1), distance=3.3, elevation=18, azimuth=-35, lens=40, floor_z=-0.75)
for i in range(6):
    joints[i + 1][0].rotation_euler.z = 0
bpy.context.view_layer.update()
tcp_world = list(round(v, 4) for v in bpy.data.objects["TCP"].matrix_world.translation)
result = {"triangles": tris, "tcp_zero_pose": tcp_world,
          "expected_tcp": [round(A2 + A3, 4), round(-(D4 + D6 + TOOL), 4), round(D1 - D5, 4)]}
