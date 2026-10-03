class_name MqttTransport
extends RefCounted
## Byte-stream transport below the MQTT client (TCP or WebSocket). Non-blocking and poll() driven.
## The base class is an in-memory loopback used by tests: bytes written by the client collect in
## `sent`, bytes for the client are injected with inject().

enum State { CLOSED, CONNECTING, OPEN }

var state := State.CLOSED
var sent: Array[PackedByteArray] = []
var _inbox := PackedByteArray()


## Starts connecting to `url`. Returns OK or an error if the URL cannot be used at all.
func open(_url: String) -> Error:
	state = State.OPEN
	return OK


func poll() -> void:
	pass


## Queues bytes for sending (never blocks). Returns false if the transport cannot accept them.
func send(data: PackedByteArray) -> bool:
	if state != State.OPEN:
		return false
	sent.append(data)
	return true


## Returns all bytes received since the last call.
func receive() -> PackedByteArray:
	var data := _inbox
	_inbox = PackedByteArray()
	return data


func close() -> void:
	state = State.CLOSED


## Best effort: tries for up to `timeout_ms` to hand queued bytes to the OS (used on shutdown only).
func flush(_timeout_ms: int) -> void:
	pass


## Test helper: bytes the "broker" sends to the client.
func inject(data: PackedByteArray) -> void:
	_inbox.append_array(data)


## Splits "scheme://host[:port][/path]" into [host, port] (`default_port` if none is given).
static func host_port(url: String, default_port: int) -> Array:
	var hostport := url.split("://", true, 1)[-1].split("/")[0]
	if not hostport.contains(":"):
		return [hostport, default_port]
	return [hostport.get_slice(":", 0), hostport.get_slice(":", 1).to_int()]


## Creates the transport for a broker URL: mqtt://host[:port] (TCP) or ws://host[:port][/path].
static func for_url(url: String) -> MqttTransport:
	if url.begins_with("ws://") or url.begins_with("wss://"):
		return MqttWebSocketTransport.new()
	if url.begins_with("mqtt://") or url.begins_with("tcp://"):
		return MqttTcpTransport.new()
	return null
