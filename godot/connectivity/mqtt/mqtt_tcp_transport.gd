class_name MqttTcpTransport
extends MqttTransport
## MQTT over plain TCP (`mqtt://host[:port]`, default port 1883) using StreamPeerTCP.
## Outgoing bytes are queued and written with put_partial_data so a full socket never blocks the frame.
## TCP_NODELAY is enabled after the first received bytes: Godot may report a refused connection as
## connected for one poll, and setting the option on such a socket prints an engine warning.

const DEFAULT_PORT := 1883

var _peer := StreamPeerTCP.new()
var _out := PackedByteArray()
var _no_delay_set := false


func open(url: String) -> Error:
	var hp := host_port(url, DEFAULT_PORT)
	_out.clear()
	_no_delay_set = false
	var err := _peer.connect_to_host(hp[0], hp[1])
	state = State.CONNECTING if err == OK else State.CLOSED
	return err


func poll() -> void:
	if state == State.CLOSED:
		return
	_peer.poll()
	match _peer.get_status():
		StreamPeerTCP.STATUS_CONNECTED:
			state = State.OPEN
			_write_pending()
		StreamPeerTCP.STATUS_CONNECTING:
			pass
		_:
			state = State.CLOSED


func send(data: PackedByteArray) -> bool:
	if state != State.OPEN:
		return false
	_out.append_array(data)
	_write_pending()
	return true


func receive() -> PackedByteArray:
	if state != State.OPEN:
		return PackedByteArray()
	var available := _peer.get_available_bytes()
	if available <= 0:
		return PackedByteArray()
	var result := _peer.get_partial_data(available)
	if result[0] != OK:
		state = State.CLOSED
		return PackedByteArray()
	if not _no_delay_set:
		_no_delay_set = true
		_peer.set_no_delay(true)
	return result[1]


func close() -> void:
	_peer.disconnect_from_host()
	_out.clear()
	state = State.CLOSED


func flush(timeout_ms: int) -> void:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while state == State.OPEN and not _out.is_empty() and Time.get_ticks_msec() < deadline:
		poll()
		OS.delay_msec(1)


func _write_pending() -> void:
	if _out.is_empty():
		return
	var result := _peer.put_partial_data(_out)
	if result[0] != OK:
		state = State.CLOSED
		return
	_out = _out.slice(result[1])
