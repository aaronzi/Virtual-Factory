class_name UnsCommands
extends RefCounted
## Commands for whitelisted inputs/tunable parameters (`commands.writable`). Messages are validated on
## receipt and queued; apply() writes them to the FMUs between master steps. Pulse variables
## (`commands.pulse`) keep the value for exactly one step, are then reset to 0 and stay 0 for one more
## step, so repeated identical commands still produce an edge in the edge-triggered PLC inputs.
## Acks: `reason` explains a rejection (empty when accepted), `v` is the applied value (null if rejected).

enum Pulse { IDLE, HOLD, COOL }

var routes := {}  # command topic -> Route
var _config: UnsConfig
var _queue: Array = []  # [Route, value, corr]


func _init(master: CoSimMaster, config: UnsConfig) -> void:
	_config = config
	var section := config.section("commands")
	var pulses: Array = section.get("pulse", [])
	var writable: Dictionary = section.get("writable", {})
	for device: String in writable:
		for var_name: String in writable[device]:
			var ep := UnsConfig.resolve(master, "%s.%s" % [device, var_name])
			if ep.is_empty() or not (ep.variable as Fmi3Variable).is_settable_in_step_mode():
				push_error("UNS: %s.%s is not a writable input/tunable parameter" % [device, var_name])
				continue
			var r := Route.new()
			r.fmu = ep.fmu
			r.variable = ep.variable
			r.device = device
			r.is_pulse = "%s.%s" % [device, var_name] in pulses
			r.ack_topic = config.topic(section.get("ack_topic", ""), device, var_name)
			routes[config.topic(section.get("topic", ""), device, var_name)] = r


func topics() -> Array:
	return routes.keys()


## Validates and queues a command. Returns an ack Dictionary to publish now if it was rejected,
## otherwise {} (the ack follows when the command is applied). Also returns the route's ack topic.
func receive(topic: String, payload: PackedByteArray) -> Array:
	var r: Route = routes.get(topic)
	if r == null:
		return []
	var json := JSON.new()
	if json.parse(payload.get_string_from_utf8()) != OK or not json.data is Dictionary:
		return [r.ack_topic, _ack(null, false, "payload must be a JSON object", null)]
	var msg: Dictionary = json.data
	var corr: Variant = msg.get("corr")
	if not msg.has(_config.value_key):
		return [r.ack_topic, _ack(corr, false, "missing '%s'" % _config.value_key, null)]
	var converted := convert_value(r.variable.type, msg[_config.value_key])
	if converted[0] != "":
		return [r.ack_topic, _ack(corr, false, converted[0], null)]
	_queue.append([r, converted[1], corr])
	return [r.ack_topic, {}]


## Applies queued commands (call before a master step). Returns [ack topic, ack] pairs to publish.
func apply() -> Array:
	for r: Route in routes.values():
		if r.pulse == Pulse.HOLD:
			r.fmu.set_value_by_vr(r.variable.value_reference, Fmi3.coerce(r.variable.type, 0))
			r.pulse = Pulse.COOL
		elif r.pulse == Pulse.COOL:
			r.pulse = Pulse.IDLE
	var acks := []
	var deferred := []
	for cmd: Array in _queue:
		var r: Route = cmd[0]
		if r.is_pulse and r.pulse != Pulse.IDLE:
			deferred.append(cmd)  # one pulse per variable at a time
			continue
		var ok := r.fmu.set_value_by_vr(r.variable.value_reference, cmd[1]) == Fmi3.Status.OK
		if ok and r.is_pulse:
			r.pulse = Pulse.HOLD
		var reason := "" if ok else "rejected by the FMU"
		acks.append([r.ack_topic, _ack(cmd[2], ok, reason, cmd[1] if ok else null)])
	_queue = deferred
	return acks


func _ack(corr: Variant, accepted: bool, reason: String, value: Variant) -> Dictionary:
	return {"corr": corr, "accepted": accepted, "reason": reason, _config.value_key: value}


## Converts a JSON value to an FMI type. Returns [error ("" if ok), converted value].
static func convert_value(type: int, value: Variant) -> Array:
	var is_number := value is float or value is int
	match type:
		Fmi3.VarType.BOOLEAN:
			if value is bool:
				return ["", value]
			if is_number and (value == 0 or value == 1):
				return ["", value == 1]
			return ["expected a boolean", null]
		Fmi3.VarType.INT32, Fmi3.VarType.UINT64:
			var low := 0.0 if type == Fmi3.VarType.UINT64 else -2147483648.0
			var high := 9.2e18 if type == Fmi3.VarType.UINT64 else 2147483647.0
			if is_number and float(value) == floorf(value) and value >= low and value <= high:
				return ["", int(value)]
			return ["expected an integer in range", null]
		Fmi3.VarType.FLOAT64:
			if is_number and is_finite(float(value)):
				return ["", float(value)]
			return ["expected a number", null]
	return ["", value] if value is String else ["expected a string", null]


## One writable variable.
class Route:
	var fmu: Fmi3CoSimulation
	var variable: Fmi3Variable
	var device := ""
	var ack_topic := ""
	var is_pulse := false
	var pulse := 0
