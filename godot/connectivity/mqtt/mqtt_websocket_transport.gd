class_name MqttWebSocketTransport
extends MqttTransport
## MQTT over WebSocket (`ws://host:port[/path]`, subprotocol "mqtt", binary frames) using WebSocketPeer.
## Before each attempt a plain TCP probe checks that the port accepts connections: a WebSocketPeer
## connecting to a closed port prints an engine warning per attempt, the probe stays silent.

const BUFFER_SIZE := 4 * 1024 * 1024

var _peer := WebSocketPeer.new()
var _probe: StreamPeerTCP
var _probe_ok_polls := 0
var _url := ""


func open(url: String) -> Error:
	_url = url
	var hp := host_port(url, 443 if url.begins_with("wss://") else 80)
	_probe = StreamPeerTCP.new()
	_probe_ok_polls = 0
	var err := _probe.connect_to_host(hp[0], hp[1])
	state = State.CONNECTING if err == OK else State.CLOSED
	return err


func poll() -> void:
	if state == State.CLOSED:
		return
	if _probe != null:
		_poll_probe()
		return
	_peer.poll()
	match _peer.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			state = State.OPEN
		WebSocketPeer.STATE_CONNECTING:
			pass
		_:
			state = State.CLOSED


func send(data: PackedByteArray) -> bool:
	if state != State.OPEN:
		return false
	return _peer.send(data, WebSocketPeer.WRITE_MODE_BINARY) == OK


func receive() -> PackedByteArray:
	var data := PackedByteArray()
	if state != State.OPEN:
		return data
	while _peer.get_available_packet_count() > 0:
		data.append_array(_peer.get_packet())
	return data


func close() -> void:
	if _probe != null:
		_probe.disconnect_from_host()
		_probe = null
	elif _peer.get_ready_state() != WebSocketPeer.STATE_CLOSED:
		_peer.close()
	state = State.CLOSED


func flush(timeout_ms: int) -> void:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while state == State.OPEN and _peer.get_current_outbound_buffered_amount() > 0 \
			and Time.get_ticks_msec() < deadline:
		poll()
		OS.delay_msec(1)


## A refused port can look connected for one poll, so the probe must stay connected for two polls.
func _poll_probe() -> void:
	_probe.poll()
	match _probe.get_status():
		StreamPeerTCP.STATUS_CONNECTING:
			return
		StreamPeerTCP.STATUS_CONNECTED:
			_probe_ok_polls += 1
			if _probe_ok_polls < 2:
				return
		_:
			_probe = null
			state = State.CLOSED
			return
	_probe.disconnect_from_host()
	_probe = null
	_open_websocket()


func _open_websocket() -> void:
	_peer = WebSocketPeer.new()
	_peer.supported_protocols = PackedStringArray(["mqtt"])
	_peer.outbound_buffer_size = BUFFER_SIZE
	_peer.inbound_buffer_size = BUFFER_SIZE
	_peer.max_queued_packets = 16384
	if _peer.connect_to_url(_url) != OK:
		state = State.CLOSED
