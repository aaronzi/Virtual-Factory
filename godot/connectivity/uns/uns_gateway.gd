class_name UnsGateway
extends RefCounted
## Unified Namespace gateway (OT edge of the virtual line, ADR-0005): publishes the session birth,
## all FMI outputs (telemetry), domain events and command acks to MQTT, and writes whitelisted
## commands into the FMUs. The contract is godot/config/uns.json (docs/interfaces/uns.md).
##
## Driven by the physics loop: before_step() polls the client and applies pending commands between
## master steps; after_step() detects events and publishes telemetry for the state after the step.
## Timestamps use the simulation time base (session start wall clock + master.time).

## Emitted for every domain event published to the broker (e.g. for the data-flow visualisation).
signal event_published(device: String, event: String)
signal command_acked(ack_topic: String, ack: Dictionary)

var session_id := ""
var layout_name := ""
## Published message counters (for diagnostics and rate measurements).
var stats := {"telemetry": 0, "events": 0, "acks": 0, "session": 0}
var telemetry: UnsTelemetry
var events: UnsEvents
var commands: UnsCommands
var _master: CoSimMaster
var _client: MqttClient
var _config: UnsConfig
var _event_seq := 0
var _birth_pending := false
var _wall_start_ms := Time.get_ticks_msec()


func _init(master: CoSimMaster, client: MqttClient, registry: Dictionary, p_layout_name: String,
		start_unix := -1.0) -> void:
	_master = master
	_client = client
	layout_name = p_layout_name
	_config = UnsConfig.new(registry, start_unix)
	session_id = _config.make_session_id()
	telemetry = UnsTelemetry.new(master, _config)
	events = UnsEvents.new(master, _config)
	commands = UnsCommands.new(master, _config)


## Configures will and subscriptions and starts connecting (non-blocking) to `url`.
func start(url: String) -> Error:
	var session := _config.section("session")
	var offline := UnsConfig.encode({_config.value_key: "offline"})
	_client.set_will(_status_topic(), offline, int(session.get("qos", 1)), session.get("retain", true))
	var qos := int(_config.section("commands").get("qos", 1))
	for topic: String in commands.topics():
		_client.subscribe(topic, qos)
	_client.connected.connect(func() -> void: _birth_pending = true)
	_client.message_received.connect(_on_message)
	return _client.connect_to_broker(url)


## Call before each master step: network I/O and commands (applied between steps).
func before_step() -> void:
	_client.poll()
	for ack: Array in commands.apply():
		_publish_ack(ack[0], ack[1])


## Call after each master step: events and telemetry of the new state.
func after_step() -> void:
	var ts := _config.timestamp(_master.time)
	for fired: Array in events.detect():
		_publish_event(fired[0], fired[1], ts)
	if not _client.is_broker_connected():
		return
	if _birth_pending:
		_birth_pending = false
		_publish_birth(ts)
		stats.telemetry += telemetry.publish(_client, _master.time, ts, true)
	else:
		stats.telemetry += telemetry.publish(_client, _master.time, ts)


## Publishes the offline status and disconnects gracefully (the will covers crashes).
func shutdown() -> void:
	if _client.is_broker_connected():
		var ts := _config.timestamp(_master.time)
		_publish_session(_status_topic(), {_config.value_key: "offline", _config.timestamp_key: ts})
	_client.disconnect_from_broker()
	var total: int = stats.values().reduce(func(a: int, b: int) -> int: return a + b, 0)
	var wall_s := (Time.get_ticks_msec() - _wall_start_ms) / 1000.0
	print("UNS: session %s published %d messages %s in %.1f s simulation / %.1f s wall time" % [
		session_id, total, JSON.stringify(stats), _master.time, wall_s])


func _publish_birth(ts: String) -> void:
	var section := _config.section("session")
	var devices := []
	for fmu in _master.get_instances():
		devices.append(fmu.instance_name)
	_publish_session(_config.topic(section.get("topic", "{root}/session")), {
		"id": session_id, "started": _config.timestamp(0.0), "layout": layout_name, "devices": devices,
		_config.timestamp_key: ts,
	})
	_publish_session(_status_topic(), {_config.value_key: "online", _config.timestamp_key: ts})


func _publish_session(topic: String, payload: Dictionary) -> void:
	var section := _config.section("session")
	if _client.publish(topic, UnsConfig.encode(payload), int(section.get("qos", 1)),
			section.get("retain", true)):
		stats.session += 1


## Events are numbered even while offline, so consumers can detect gaps.
func _publish_event(d: UnsEvents.Definition, fields: Dictionary, ts: String) -> void:
	_event_seq += 1
	if not _client.is_broker_connected():
		return
	var payload := {"event": d.event, "device": d.device, "session": session_id, "seq": _event_seq,
		_config.timestamp_key: ts}
	payload.merge(fields)
	var section := _config.section("events")
	if _client.publish(d.topic, UnsConfig.encode(payload), int(section.get("qos", 1)),
			section.get("retain", false)):
		stats.events += 1
		event_published.emit(d.device, d.event)


func _on_message(topic: String, payload: PackedByteArray) -> void:
	var result := commands.receive(topic, payload)
	if not result.is_empty() and not (result[1] as Dictionary).is_empty():
		_publish_ack(result[0], result[1])


func _publish_ack(topic: String, ack: Dictionary) -> void:
	ack[_config.timestamp_key] = _config.timestamp(_master.time)
	var section := _config.section("commands")
	if _client.publish(topic, UnsConfig.encode(ack), int(section.get("qos", 1)),
			section.get("retain", false)):
		stats.acks += 1
		command_acked.emit(topic, ack)


func _status_topic() -> String:
	return _config.topic(_config.section("session").get("status_topic", "{root}/status"))


## Registry view shared with the backplane link (same time base, OPC UA device split).
func get_config() -> UnsConfig:
	return _config


func is_broker_connected() -> bool:
	return _client.is_broker_connected()
