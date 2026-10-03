class_name UnsConfig
extends RefCounted
## Typed view of the UNS registry (godot/config/uns.json): topic templates, payload keys, QoS/retain,
## and timestamps on the simulation time base (session start wall clock + simulation time).
## `opcua_devices`: controllers on the OPC UA path (`opcua.servers` while `opcua.enabled`, ADR-0024); the
## UNS gateway leaves their telemetry, events and commands to the backplane link (PlcBackplane).

var data: Dictionary
var root := ""
var value_key := "v"
var timestamp_key := "ts"
var start_unix := 0.0
var opcua_devices: Array = []


func _init(p_data: Dictionary, p_start_unix := -1.0) -> void:
	data = p_data
	root = data.get("topic_root", "vf")
	var payload: Dictionary = data.get("payload", {})
	value_key = payload.get("value_key", "v")
	timestamp_key = payload.get("timestamp_key", "ts")
	start_unix = p_start_unix if p_start_unix >= 0.0 else Time.get_unix_time_from_system()
	var opcua: Dictionary = data.get("opcua", {})
	if opcua.get("enabled", false):
		opcua_devices = (opcua.get("servers", {}) as Dictionary).keys()


## True if `device` belongs to the selected path: OPC UA (`opcua`) or direct MQTT publishing.
func on_path(device: String, opcua: bool) -> bool:
	return (device in opcua_devices) == opcua


## Section of the registry ("session", "telemetry", "events", "commands").
func section(section_name: String) -> Dictionary:
	return data.get(section_name, {})


## Expands a template: {root}, {device} (lower-case instance name), {variable} and {event} (= leaf).
func topic(template: String, device := "", leaf := "") -> String:
	return template.format({"root": root, "device": device.to_lower(), "variable": leaf, "event": leaf})


## ISO 8601 UTC timestamp with milliseconds for a simulation time.
func timestamp(sim_time: float) -> String:
	var total_ms := roundi((start_unix + sim_time) * 1000.0)
	var date := Time.get_datetime_string_from_unix_time(floori(total_ms / 1000.0))
	return "%s.%03dZ" % [date, total_ms % 1000]


## Session id like S-20261003T131500Z-3fa2 (start time + random suffix).
func make_session_id() -> String:
	var start := Time.get_datetime_string_from_unix_time(floori(start_unix)).replace("-", "").replace(":", "")
	return "S-%sZ-%04x" % [start, randi() & 0xFFFF]


## Splits "INSTANCE.variable" and resolves it in the master: {"fmu", "variable"} or {}.
static func resolve(master: CoSimMaster, path: String) -> Dictionary:
	var parts := path.split(".", true, 1)
	var fmu: Fmi3CoSimulation = master.get_instance(parts[0]) if parts.size() == 2 else null
	var v: Fmi3Variable = fmu.model_description.get_variable(parts[1]) if fmu != null else null
	return {"fmu": fmu, "variable": v} if v != null else {}


## Compact JSON payload; keys keep their insertion order.
static func encode(payload: Dictionary) -> PackedByteArray:
	return JSON.stringify(payload, "", false).to_utf8_buffer()


## JSON-safe value (non-finite floats become null).
static func json_value(value: Variant) -> Variant:
	if value is float and not is_finite(value):
		return null
	return value
