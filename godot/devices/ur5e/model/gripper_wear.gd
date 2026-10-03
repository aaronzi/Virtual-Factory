class_name Ur5eGripperWear
extends RefCounted
## Wear of the gripper fingers (V-jaw pads of GR01), evaluated once per grip on a part. Abrasive wear
## grows linearly with the gripping cycles (Archard: proportional to clamping force x sliding distance,
## both constant per grip) at `rate` metres per grip (5 % scatter). Symptoms as a smart gripper reports
## them over the robot's tool I/O:
##   measured_wear  jaw position offset at contact against the taught part width [m] (encoder, sigma 3 um)
##   force          clamping force of the last grip [N]: nominal x (1 - 0.3 wear/limit), sigma 0.8 N
##                  (rising spindle and guide friction of the worn jaws)
##   speed_factor   jaw speed x (1 - 0.25 wear/limit); the jaws also travel 2 x wear further
## Grip security: below 85 % of the wear limit a gripped part never slips; above, a grip slips with
## probability (wear/limit - 0.85) / 0.3 (50 % at the limit, always from 115 %). The robot program
## regrips a slipped part; it fails only when all attempts slip. A finger change (`replace_fingers`)
## restores new pads.
## Pure model (no scene tree), deterministic with the seed.

const FORCE_LOSS := 0.3
const SPEED_LOSS := 0.25
const SLIP_START := 0.85
const SLIP_SPAN := 0.3
const SCATTER := 0.05
const WEAR_NOISE := 3e-6
const FORCE_NOISE := 0.8

var rate := 4e-10  ## m per grip
var limit := 1e-3  ## m (wear allowance of the pads)
var nominal_force := 100.0  ## N
var wear := 0.0  ## true wear [m]
var measured_wear := 0.0
var force := 0.0
var cycles := 0  ## grips since the last finger change
var retries := 0  ## slipped grips (regrips) since the last finger change
var _rng := RandomNumberGenerator.new()


func _init(p_seed := 0, start_wear := 0.0, p_nominal_force := 100.0) -> void:
	_rng.seed = p_seed
	nominal_force = p_nominal_force
	wear = start_wear
	measured_wear = start_wear
	force = nominal_force * (1.0 - FORCE_LOSS * ratio())


## Wear relative to the allowance (1 = limit reached).
func ratio() -> float:
	return wear / limit if limit > 0.0 else 0.0


## One grip (the jaws close on a part): wears the pads, updates the symptoms. Returns true if the part
## is held, false if it slipped (the program regrips).
func grip() -> bool:
	cycles += 1
	wear += rate * maxf(0.0, 1.0 + SCATTER * _rng.randfn())
	measured_wear = maxf(0.0, wear + WEAR_NOISE * _rng.randfn())
	force = nominal_force * (1.0 - FORCE_LOSS * minf(ratio(), 1.5)) + FORCE_NOISE * _rng.randfn()
	var slip := clampf((ratio() - SLIP_START) / SLIP_SPAN, 0.0, 1.0)
	var held := _rng.randf() >= slip
	if not held:
		retries += 1
	return held


## Jaw speed relative to new fingers.
func speed_factor() -> float:
	return 1.0 - SPEED_LOSS * minf(ratio(), 1.5)


## Extra closing travel per jaw [m]: worn pads touch the part later.
func contact_offset() -> float:
	return wear


## Finger change: new pads, the gripper's maintenance counters restart.
func replace_fingers() -> void:
	wear = 0.0
	measured_wear = 0.0
	cycles = 0
	retries = 0
	force = nominal_force


func save() -> Dictionary:
	return {"wear": wear, "measured": measured_wear, "force": force, "cycles": cycles, "retries": retries,
		"rng": _rng.state}


func load(s: Dictionary) -> void:
	wear = s.get("wear", wear)
	measured_wear = s.get("measured", measured_wear)
	force = s.get("force", force)
	cycles = s.get("cycles", cycles)
	retries = s.get("retries", retries)
	_rng.state = s.get("rng", _rng.state)
