class_name UnsTelemetry
extends RefCounted
## Publishes every FMI output of every co-simulation instance on change (retained):
## discrete values immediately, continuous Float64 values at most every `min_interval_s` of simulation
## time (the latest value is sent once the interval has elapsed).


var points: Array[Point] = []
var _config: UnsConfig
var _qos := 0
var _retain := true
var _interval := 0.1


## `opcua`: only the devices on the OPC UA path (default: only the directly published ones).
func _init(master: CoSimMaster, config: UnsConfig, opcua := false) -> void:
	_config = config
	var section := config.section("telemetry")
	_qos = int(section.get("qos", 0))
	_retain = section.get("retain", true)
	_interval = float(section.get("min_interval_s", 0.1))
	var template: String = section.get("topic", "{root}/{device}/{variable}")
	for fmu in master.get_instances():
		if not config.on_path(fmu.instance_name, opcua):
			continue
		for v in fmu.model_description.variables:
			if v.is_output():
				points.append(Point.new(fmu, v, config.topic(template, fmu.instance_name, v.name)))


## Publishes changed values (all values if `full`). Returns the number of messages sent.
func publish(client: MqttClient, sim_time: float, ts: String, full := false) -> int:
	var count := 0
	for p in points:
		var value: Variant = p.fmu.get_value_by_vr(p.vr)
		if not full and p.sent:
			if value == p.last or (p.throttled and sim_time - p.last_time < _interval - 1e-9):
				continue
		var payload := {_config.value_key: UnsConfig.json_value(value), _config.timestamp_key: ts}
		if not client.publish(p.topic, UnsConfig.encode(payload), _qos, _retain):
			return count
		p.sent = true
		p.last = value
		p.last_time = sim_time
		count += 1
	return count


## One published output.
class Point:
	var fmu: Fmi3CoSimulation
	var vr := 0
	var topic := ""
	var throttled := false
	var sent := false
	var last: Variant
	var last_time := 0.0

	func _init(p_fmu: Fmi3CoSimulation, v: Fmi3Variable, p_topic: String) -> void:
		fmu = p_fmu
		vr = v.value_reference
		topic = p_topic
		throttled = v.type == Fmi3.VarType.FLOAT64 and v.variability == Fmi3.Variability.CONTINUOUS

