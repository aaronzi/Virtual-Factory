class_name MqttStreamParser
extends RefCounted
## Incremental MQTT packet parser: feed() arbitrary byte chunks (fragments or several packets per
## read), then call next() until it returns {}. A malformed stream sets `error` (connection must close).

var error := ""
var _buffer := PackedByteArray()


func feed(data: PackedByteArray) -> void:
	_buffer.append_array(data)


## Returns the next complete packet (see MqttPacket.decode) or {} if more bytes are needed.
func next() -> Dictionary:
	if error != "" or _buffer.is_empty():
		return {}
	var packet := MqttPacket.decode(_buffer)
	if packet.has("error"):
		error = packet.error
		return {}
	if not packet.is_empty():
		_buffer = _buffer.slice(packet.size)
	return packet


func reset() -> void:
	error = ""
	_buffer.clear()


func buffered_bytes() -> int:
	return _buffer.size()
