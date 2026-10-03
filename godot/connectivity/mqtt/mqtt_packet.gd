class_name MqttPacket
extends RefCounted
## MQTT 3.1.1 packet codec (OASIS standard, subset used by the UNS gateway). Pure static functions.
##
## Encoders return complete packets (fixed header + remaining length + body). decode() parses one
## packet from the start of a byte buffer and returns a Dictionary:
##   {} = incomplete (wait for more bytes); {"error": msg} = malformed stream;
##   otherwise {"type": Type, "flags": int, "size": bytes consumed, ...type specific fields}.

enum Type {
	CONNECT = 1, CONNACK = 2, PUBLISH = 3, PUBACK = 4, SUBSCRIBE = 8, SUBACK = 9,
	PINGREQ = 12, PINGRESP = 13, DISCONNECT = 14,
}

const PROTOCOL_LEVEL := 4  # MQTT 3.1.1
const MAX_REMAINING_LENGTH := 268435455
const VARINT_INCOMPLETE := -1
const VARINT_MALFORMED := -2


# --- primitives ---------------------------------------------------------------------------------

## Encodes the "remaining length" variable byte integer (1..4 bytes).
static func encode_varint(value: int) -> PackedByteArray:
	assert(value >= 0 and value <= MAX_REMAINING_LENGTH, "MQTT remaining length out of range")
	var out := PackedByteArray()
	while true:
		var digit := value & 0x7F
		value = value >> 7
		if value > 0:
			digit |= 0x80
		out.append(digit)
		if value == 0:
			break
	return out


## Decodes a variable byte integer at `offset`. Returns [value, byte count]; value is
## VARINT_INCOMPLETE if more bytes are needed or VARINT_MALFORMED if longer than 4 bytes.
static func decode_varint(buffer: PackedByteArray, offset := 0) -> Array:
	var value := 0
	var multiplier := 1
	for i in 4:
		if offset + i >= buffer.size():
			return [VARINT_INCOMPLETE, 0]
		var digit := buffer[offset + i]
		value += (digit & 0x7F) * multiplier
		if digit & 0x80 == 0:
			return [value, i + 1]
		multiplier *= 128
	return [VARINT_MALFORMED, 0]


static func encode_string(text: String) -> PackedByteArray:
	return encode_bytes(text.to_utf8_buffer())


## Binary data with a two-byte big-endian length prefix (strings, will payload).
static func encode_bytes(data: PackedByteArray) -> PackedByteArray:
	var out := encode_u16(data.size())
	out.append_array(data)
	return out


static func encode_u16(value: int) -> PackedByteArray:
	return PackedByteArray([(value >> 8) & 0xFF, value & 0xFF])


static func read_u16(buffer: PackedByteArray, offset: int) -> int:
	return (buffer[offset] << 8) | buffer[offset + 1]


# --- encoders -----------------------------------------------------------------------------------

## CONNECT with clean session. `will` (optional): {"topic", "payload": PackedByteArray, "qos", "retain"}.
static func connect_packet(client_id: String, keepalive_s: int, will := {}) -> PackedByteArray:
	var body := encode_string("MQTT")
	var flags := 0x02
	if not will.is_empty():
		flags |= 0x04 | (int(will.get("qos", 0)) << 3) | (0x20 if will.get("retain", false) else 0)
	body.append_array(PackedByteArray([PROTOCOL_LEVEL, flags]))
	body.append_array(encode_u16(keepalive_s))
	body.append_array(encode_string(client_id))
	if not will.is_empty():
		body.append_array(encode_string(will.topic))
		body.append_array(encode_bytes(will.payload))
	return _packet(Type.CONNECT << 4, body)


static func connack_packet(return_code: int, session_present := false) -> PackedByteArray:
	return _packet(Type.CONNACK << 4, PackedByteArray([1 if session_present else 0, return_code]))


## PUBLISH; `packet_id` is required (1..65535) for QoS 1.
static func publish_packet(topic: String, payload: PackedByteArray, qos := 0, retain := false,
		packet_id := 0, dup := false) -> PackedByteArray:
	var header := (Type.PUBLISH << 4) | (qos << 1) | (0x08 if dup else 0) | (0x01 if retain else 0)
	var body := encode_string(topic)
	if qos > 0:
		body.append_array(encode_u16(packet_id))
	body.append_array(payload)
	return _packet(header, body)


static func puback_packet(packet_id: int) -> PackedByteArray:
	return _packet(Type.PUBACK << 4, encode_u16(packet_id))


## SUBSCRIBE for a Dictionary {topic filter: requested QoS}.
static func subscribe_packet(packet_id: int, filters: Dictionary) -> PackedByteArray:
	var body := encode_u16(packet_id)
	for topic: String in filters:
		body.append_array(encode_string(topic))
		body.append(int(filters[topic]))
	return _packet((Type.SUBSCRIBE << 4) | 0x02, body)


static func suback_packet(packet_id: int, return_codes: PackedByteArray) -> PackedByteArray:
	var body := encode_u16(packet_id)
	body.append_array(return_codes)
	return _packet(Type.SUBACK << 4, body)


static func pingreq_packet() -> PackedByteArray:
	return PackedByteArray([Type.PINGREQ << 4, 0])


static func pingresp_packet() -> PackedByteArray:
	return PackedByteArray([Type.PINGRESP << 4, 0])


static func disconnect_packet() -> PackedByteArray:
	return PackedByteArray([Type.DISCONNECT << 4, 0])


# --- decoder ------------------------------------------------------------------------------------

## Parses the packet at the start of `buffer` (see class doc for the result format).
static func decode(buffer: PackedByteArray) -> Dictionary:
	if buffer.size() < 2:
		return {}
	var length := decode_varint(buffer, 1)
	if length[0] == VARINT_MALFORMED:
		return {"error": "malformed remaining length"}
	if length[0] == VARINT_INCOMPLETE:
		return {}
	var start: int = 1 + length[1]
	var size: int = start + length[0]
	if buffer.size() < size:
		return {}
	var packet := {"type": buffer[0] >> 4, "flags": buffer[0] & 0x0F, "size": size}
	var body := buffer.slice(start, size)
	var err := _decode_body(packet, body)
	return {"error": err} if err != "" else packet


static func _decode_body(p: Dictionary, body: PackedByteArray) -> String:
	match p.type:
		Type.CONNACK:
			if body.size() != 2:
				return "bad CONNACK"
			p.session_present = body[0] & 0x01 == 1
			p.return_code = body[1]
		Type.PUBLISH:
			return _decode_publish(p, body)
		Type.PUBACK:
			if body.size() != 2:
				return "bad PUBACK"
			p.packet_id = read_u16(body, 0)
		Type.SUBACK:
			if body.size() < 3:
				return "bad SUBACK"
			p.packet_id = read_u16(body, 0)
			p.return_codes = body.slice(2)
		Type.CONNECT, Type.SUBSCRIBE:
			p.body = body  # server-side packets: kept raw (only needed by tests)
	return ""


static func _decode_publish(p: Dictionary, body: PackedByteArray) -> String:
	p.qos = (p.flags >> 1) & 0x03
	p.retain = p.flags & 0x01 == 1
	p.dup = p.flags & 0x08 != 0
	if body.size() < 2:
		return "bad PUBLISH"
	var topic_len := read_u16(body, 0)
	var pos := 2 + topic_len
	if p.qos == 3 or body.size() < pos + (2 if p.qos > 0 else 0):
		return "bad PUBLISH"
	p.topic = body.slice(2, pos).get_string_from_utf8()
	p.packet_id = 0
	if p.qos > 0:
		p.packet_id = read_u16(body, pos)
		pos += 2
	p.payload = body.slice(pos)
	return ""


static func _packet(header: int, body: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray([header])
	out.append_array(encode_varint(body.size()))
	out.append_array(body)
	return out
