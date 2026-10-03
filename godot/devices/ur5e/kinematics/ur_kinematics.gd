class_name UrKinematics
extends RefCounted
## Forward and closed-form inverse kinematics of the Universal Robots UR5e (standard DH, Z-up base
## frame, metres/radians). IK after K. P. Hawkins, "Analytic Inverse Kinematics for the Universal
## Robots UR-5/UR-10 Arms" (2013): up to 8 solutions (shoulder, wrist, elbow branches).

const D1 := 0.1625
const A2 := -0.425
const A3 := -0.3922
const D4 := 0.1333
const D5 := 0.0997
const D6 := 0.0996
const D := [D1, 0.0, 0.0, D4, D5, D6]
const A := [0.0, A2, A3, 0.0, 0.0, 0.0]
const ALPHA := [PI / 2.0, 0.0, 0.0, PI / 2.0, -PI / 2.0, 0.0]
const JOINT_LIMIT := TAU  ## ±360° on all joints


## DH transform of link i (0-based) for joint angle theta.
static func dh(i: int, theta: float) -> Transform3D:
	return _dh(theta, D[i], A[i], ALPHA[i])


## Flange pose in the base frame.
static func forward(q: PackedFloat64Array) -> Transform3D:
	var t := Transform3D.IDENTITY
	for i in 6:
		t = t * dh(i, q[i])
	return t


## Poses of frames 1..6 in the base frame (for visualisation).
static func forward_frames(q: PackedFloat64Array) -> Array[Transform3D]:
	var frames: Array[Transform3D] = []
	var t := Transform3D.IDENTITY
	for i in 6:
		t = t * dh(i, q[i])
		frames.append(t)
	return frames


## All IK solutions for a flange pose (angles wrapped to (-PI, PI]).
static func inverse(t: Transform3D) -> Array[PackedFloat64Array]:
	var sols: Array[PackedFloat64Array] = []
	var p05 := t * Vector3(0, 0, -D6)
	var r := Vector2(p05.x, p05.y).length()
	if r < D4:
		return sols
	var psi := atan2(p05.y, p05.x)
	var phi := acos(D4 / r)
	for t1 in [psi + phi + PI / 2.0, psi - phi + PI / 2.0]:
		var c5 := (t.origin.x * sin(t1) - t.origin.y * cos(t1) - D4) / D6
		if absf(c5) > 1.0 + 1e-9:
			continue
		for sign5 in [1.0, -1.0]:
			var t5: float = sign5 * acos(clampf(c5, -1.0, 1.0))
			_solve_arm(t, t1, t5, sols)
	return sols


## The solution closest to `ref` (joint-space distance), each joint shifted by ±2π towards `ref`
## within the joint limits. Returns an empty array if `t` is unreachable.
static func inverse_closest(t: Transform3D, ref: PackedFloat64Array) -> PackedFloat64Array:
	var best := PackedFloat64Array()
	var best_dist := INF
	for sol in inverse(t):
		var cand := PackedFloat64Array()
		var dist := 0.0
		for i in 6:
			var a := ref[i] + wrapf(sol[i] - ref[i], -PI, PI)
			if absf(a) > JOINT_LIMIT:
				a -= signf(a) * TAU
			cand.append(a)
			dist += (a - ref[i]) * (a - ref[i])
		if dist < best_dist:
			best_dist = dist
			best = cand
	return best


static func _solve_arm(t: Transform3D, t1: float, t5: float, sols: Array[PackedFloat64Array]) -> void:
	var s1 := sin(t1)
	var c1 := cos(t1)
	var s5 := sin(t5)
	var t6 := 0.0
	if absf(s5) > 1e-6:
		# X60, Y60 = first/second column of R06^T = first/second row of R06
		var x60x := t.basis.x.x
		var x60y := t.basis.y.x
		var y60x := t.basis.x.y
		var y60y := t.basis.y.y
		t6 = atan2((-x60y * s1 + y60y * c1) / s5, (x60x * s1 - y60x * c1) / s5)
	var t14 := dh(0, t1).affine_inverse() * t * (dh(4, t5) * dh(5, t6)).affine_inverse()
	var p13 := t14 * Vector3(0, -D4, 0)
	var len13 := p13.length()
	var c3 := (len13 * len13 - A2 * A2 - A3 * A3) / (2.0 * A2 * A3)
	if absf(c3) > 1.0 + 1e-9:
		return
	for sign3 in [1.0, -1.0]:
		var t3: float = sign3 * acos(clampf(c3, -1.0, 1.0))
		var t2 := -atan2(p13.y, -p13.x) + asin(clampf(A3 * sin(t3) / len13, -1.0, 1.0))
		var t34 := (dh(1, t2) * dh(2, t3)).affine_inverse() * t14
		var t4 := atan2(t34.basis.x.y, t34.basis.x.x)
		sols.append(PackedFloat64Array([
			wrapf(t1, -PI, PI), wrapf(t2, -PI, PI), wrapf(t3, -PI, PI),
			wrapf(t4, -PI, PI), wrapf(t5, -PI, PI), wrapf(t6, -PI, PI)]))


static func _dh(theta: float, d: float, a: float, alpha: float) -> Transform3D:
	var ct := cos(theta)
	var st := sin(theta)
	var ca := cos(alpha)
	var sa := sin(alpha)
	return Transform3D(
		Basis(Vector3(ct, st, 0.0), Vector3(-st * ca, ct * ca, sa), Vector3(st * sa, -ct * sa, ca)),
		Vector3(a * ct, a * st, d))


## Preferred configuration for a pose without a reference (e.g. the home pose at start-up):
## elbow up (highest elbow), then wrist 2 negative. Empty if unreachable.
static func inverse_preferred(t: Transform3D) -> PackedFloat64Array:
	var best := PackedFloat64Array()
	var best_score := -INF
	for sol in inverse(t):
		var elbow_z := forward_frames(sol)[1].origin.z
		var score := elbow_z * 10.0 + (0.1 if sol[4] < 0.0 else 0.0)
		if score > best_score:
			best_score = score
			best = sol
	return best
