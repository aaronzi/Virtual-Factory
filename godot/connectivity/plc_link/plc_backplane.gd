class_name PlcBackplane
extends RefCounted
## Backplane link of the simulated PLC CPU (a controller FMU) to its communication module, the separate
## OPC UA server process plc-comm (ADR-0024). Newline-delimited JSON over TCP; the protocol is described
## in services/plc_comm/src/plc_comm/backplane.py and docs/interfaces/uns.md.
##   after_step()   hello after (re)connecting; once the module answered with welcome: events of the tick
##                  and the changed process image (all values after welcome)
##   before_step()  network I/O; writes from the module (OPC UA method calls) are validated and applied
##                  between master steps like UNS commands (UnsCommands: types, pulse inputs) and answered
## Reconnects with backoff (1 .. 10 s). Nothing is buffered while unlinked (comm module down = PLC
## offline on OPC UA); events are numbered anyway, so gaps show in `seq`.

signal event_sent(device: String, event: String)
signal write_applied(device: String, accepted: bool)

const PROTOCOL := 1
const MIN_BACKOFF_S := 1.0
const MAX_BACKOFF_S := 10.0

var device := ""
var session_id := ""
var url := ""
## Sent/received message counters (diagnostics, rate measurements).
var stats := {"images": 0, "events": 0, "writes": 0}
var _master: CoSimMaster
var _config: UnsConfig
var _fmu: Fmi3CoSimulation
var _image: PlcProcessImage
var _events: UnsEvents
var _commands: UnsCommands
var _transport: MqttTransport
var _rx := PackedByteArray()
var _hello_pending := false
var _full_pending := false
var _connected := false
var _welcomed := false
var _event_seq := 0
var _backoff_s := MIN_BACKOFF_S
var _retry_at_ms := 0
var _outage_warned := false


func _init(master: CoSimMaster, config: UnsConfig, p_device: String, p_session_id: String) -> void:
	_master = master
	_config = config
	device = p_device
	session_id = p_session_id
	_fmu = master.get_instance(device)
	_image = PlcProcessImage.new(_fmu)
	_events = UnsEvents.new(master, config, true)
	_commands = UnsCommands.new(master, config, true)


## Starts connecting to tcp://host:port (non-blocking). `transport` overrides the TCP transport (tests).
## The byte transports of the MQTT client are generic streams and are reused here.
func start(p_url: String, transport: MqttTransport = null) -> Error:
	_transport = transport if transport != null else MqttTransport.for_url(p_url)
	if _transport == null or _fmu == null:
		push_warning("Backplane: cannot link %s to '%s'" % [device, p_url])
		return ERR_INVALID_PARAMETER
	url = p_url
	_retry_at_ms = 0
	return OK


## True once the communication module has answered the hello (a TCP connect alone is not enough: a
## refused connection may look open for one poll).
func is_linked() -> bool:
	return _welcomed and _transport != null and _transport.state == MqttTransport.State.OPEN


## Call before each master step: connection handling, writes from the communication module.
func before_step() -> void:
	if _transport == null:
		return
	_poll_connection()
	if not _connected:
		return
	_rx.append_array(_transport.receive())
	var newline := _rx.find(10)
	while newline >= 0:
		_handle(_rx.slice(0, newline).get_string_from_utf8())
		_rx = _rx.slice(newline + 1)
		newline = _rx.find(10)
	for ack: Array in _commands.apply():
		_result(ack[1])


## Call after each master step: events of the tick and the changed process image.
func after_step() -> void:
	var fired := _events.detect()
	if _hello_pending and _connected:
		_hello_pending = false
		_send({"type": "hello", "protocol": PROTOCOL, "device": device, "session": session_id,
			"model": _fmu.model_description.model_name, "variables": _image.size()})
	if not is_linked():
		_event_seq += fired.size()
		return
	var ts := _config.timestamp(_master.time)
	var full := _full_pending
	_full_pending = false
	for event: Array in fired:
		_send_event(event[0], event[1], ts)
	var values := _image.changes(full)
	if not values.is_empty():
		_send({"type": "image", "ts": ts, "values": values})
		stats.images += 1


func shutdown() -> void:
	if _transport != null:
		_transport.flush(200)
		_transport.close()
	print("Backplane: %s %s" % [device, JSON.stringify(stats)])


func _poll_connection() -> void:
	if _transport.state == MqttTransport.State.CLOSED and Time.get_ticks_msec() >= _retry_at_ms:
		if _retry_at_ms > 0:
			_warn_outage()
		_retry_at_ms = Time.get_ticks_msec() + int(_backoff_s * 1000.0)
		_backoff_s = minf(_backoff_s * 2.0, MAX_BACKOFF_S)
		_rx.clear()
		_transport.close()
		_transport.open(url)
	_transport.poll()
	var open := _transport.state == MqttTransport.State.OPEN
	if open and not _connected:
		_hello_pending = true
	elif not open:
		_welcomed = false
	_connected = open


func _welcome(msg: Dictionary) -> void:
	_welcomed = true
	_full_pending = true
	_backoff_s = MIN_BACKOFF_S
	_outage_warned = false
	print("Backplane: %s linked to %s (OPC UA %s)" % [device, url, msg.get("endpoint", "?")])


func _warn_outage() -> void:
	if not _outage_warned:
		_outage_warned = true
		push_warning("Backplane: communication module of %s not reachable at %s (retrying)" % [device, url])


func _handle(line: String) -> void:
	var msg: Variant = JSON.parse_string(line)
	if msg is Dictionary and msg.get("type") == "welcome":
		_welcome(msg)
	if not msg is Dictionary or msg.get("type") != "write":
		return
	var variable: String = str(msg.get("variable", ""))
	var topic := _config.topic(_config.section("commands").get("topic", ""), device, variable)
	var payload := UnsConfig.encode({_config.value_key: msg.get("v"), "corr": msg.get("id")})
	var result := _commands.receive(topic, payload)
	if result.is_empty():
		_result({"corr": msg.get("id"), "accepted": false, "reason": "%s is not writable" % variable})
	elif not (result[1] as Dictionary).is_empty():
		_result(result[1])


func _result(ack: Dictionary) -> void:
	stats.writes += 1
	_send({"type": "result", "id": ack.get("corr"), "accepted": ack.get("accepted", false),
		"reason": ack.get("reason", ""), "v": ack.get(_config.value_key)})
	write_applied.emit(device, ack.get("accepted", false))


func _send_event(d: UnsEvents.Definition, fields: Dictionary, ts: String) -> void:
	_event_seq += 1
	var payload := {"event": d.event, "device": d.device, "session": session_id, "seq": _event_seq,
		_config.timestamp_key: ts}
	payload.merge(fields)
	_send({"type": "event", "event": d.event, "ts": ts, "payload": payload})
	stats.events += 1
	event_sent.emit(d.device, d.event)


func _send(msg: Dictionary) -> void:
	var bytes := UnsConfig.encode(msg)
	bytes.append(10)
	_transport.send(bytes)
