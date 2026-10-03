extends GutTest

const P := preload("res://connectivity/mqtt/mqtt_packet.gd")


func test_varint_edge_cases() -> void:
	var cases := {
		0: [0x00], 127: [0x7F], 128: [0x80, 0x01], 16383: [0xFF, 0x7F], 16384: [0x80, 0x80, 0x01],
		2097151: [0xFF, 0xFF, 0x7F], 2097152: [0x80, 0x80, 0x80, 0x01], 268435455: [0xFF, 0xFF, 0xFF, 0x7F],
	}
	for value: int in cases:
		var encoded := P.encode_varint(value)
		assert_eq(encoded, PackedByteArray(cases[value]), "encode %d" % value)
		assert_eq(P.decode_varint(encoded), [value, encoded.size()], "decode %d" % value)


func test_varint_incomplete_and_malformed() -> void:
	assert_eq(P.decode_varint(PackedByteArray([0x80]))[0], P.VARINT_INCOMPLETE)
	assert_eq(P.decode_varint(PackedByteArray([]))[0], P.VARINT_INCOMPLETE)
	assert_eq(P.decode_varint(PackedByteArray([0x80, 0x80, 0x80, 0x80, 0x01]))[0], P.VARINT_MALFORMED)
	assert_eq(P.decode_varint(PackedByteArray([0x00, 0x80, 0x01]), 1), [128, 2], "offset")


func test_connect_without_will() -> void:
	var expected := PackedByteArray([0x10, 16, 0, 4, 77, 81, 84, 84, 4, 0x02, 0, 60, 0, 4]) \
		+ "vf-1".to_utf8_buffer()
	assert_eq(P.connect_packet("vf-1", 60), expected)


func test_connect_with_will() -> void:
	var will := {"topic": "a/s", "payload": "off".to_utf8_buffer(), "qos": 1, "retain": true}
	var packet := P.connect_packet("c", 30, will)
	var decoded := P.decode(packet)
	assert_eq(decoded.type, P.Type.CONNECT)
	assert_eq(decoded.size, packet.size())
	assert_eq(packet[9], 0x02 | 0x04 | 0x08 | 0x20, "clean session + will flag + will QoS 1 + will retain")
	var body: PackedByteArray = decoded.body
	assert_eq(body.slice(10), PackedByteArray([0, 1, 99, 0, 3]) + "a/s".to_utf8_buffer()
		+ PackedByteArray([0, 3]) + "off".to_utf8_buffer())


func test_publish_round_trip_qos0_and_qos1() -> void:
	var payload := '{"v": 1.5}'.to_utf8_buffer()
	var q0 := P.decode(P.publish_packet("vf/x/y", payload, 0, true))
	assert_eq([q0.type, q0.topic, q0.payload, q0.qos, q0.retain, q0.packet_id],
		[P.Type.PUBLISH, "vf/x/y", payload, 0, true, 0])
	var q1 := P.decode(P.publish_packet("ü/t", payload, 1, false, 4711))
	assert_eq([q1.topic, q1.payload, q1.qos, q1.retain, q1.packet_id], ["ü/t", payload, 1, false, 4711])


func test_large_publish_uses_multibyte_length() -> void:
	var payload := PackedByteArray()
	payload.resize(20000)
	var packet := P.publish_packet("t", payload)
	assert_eq(packet[1] & 0x80, 0x80)
	var decoded := P.decode(packet)
	assert_eq(decoded.payload.size(), 20000)
	assert_eq(decoded.size, packet.size())


func test_small_packets() -> void:
	assert_eq(P.decode(P.puback_packet(258)).packet_id, 258)
	assert_eq(P.puback_packet(258), PackedByteArray([0x40, 2, 1, 2]))
	var connack := P.decode(P.connack_packet(5, true))
	assert_eq([connack.type, connack.return_code, connack.session_present], [P.Type.CONNACK, 5, true])
	assert_eq(P.pingreq_packet(), PackedByteArray([0xC0, 0]))
	assert_eq(P.decode(P.pingresp_packet()).type, P.Type.PINGRESP)
	assert_eq(P.disconnect_packet(), PackedByteArray([0xE0, 0]))


func test_subscribe_and_suback() -> void:
	var packet := P.subscribe_packet(7, {"a/b": 1, "c": 0})
	assert_eq(packet[0], 0x82, "SUBSCRIBE has reserved flags 0010")
	assert_eq(packet.slice(2), PackedByteArray([0, 7, 0, 3]) + "a/b".to_utf8_buffer()
		+ PackedByteArray([1, 0, 1]) + "c".to_utf8_buffer() + PackedByteArray([0]))
	var suback := P.decode(P.suback_packet(7, PackedByteArray([1, 0x80])))
	assert_eq([suback.packet_id, suback.return_codes], [7, PackedByteArray([1, 0x80])])


func test_stream_parser_fragmented_bytes() -> void:
	var parser := MqttStreamParser.new()
	var stream := P.publish_packet("a", "hello".to_utf8_buffer(), 1, false, 9) + P.pingresp_packet()
	var packets := []
	for b in stream:
		parser.feed(PackedByteArray([b]))
		var p := parser.next()
		if not p.is_empty():
			packets.append(p)
	assert_eq(packets.size(), 2)
	assert_eq(packets[0].payload.get_string_from_utf8(), "hello")
	assert_eq(packets[1].type, P.Type.PINGRESP)
	assert_eq(parser.buffered_bytes(), 0)


func test_stream_parser_several_packets_per_read() -> void:
	var parser := MqttStreamParser.new()
	var big := PackedByteArray()
	big.resize(300)
	var last := P.publish_packet("y", PackedByteArray([7, 8]))
	parser.feed(P.connack_packet(0) + P.publish_packet("x", big) + P.puback_packet(1) + last.slice(0, 3))
	var types := []
	var p := parser.next()
	while not p.is_empty():
		types.append(p.type)
		p = parser.next()
	assert_eq(types, [P.Type.CONNACK, P.Type.PUBLISH, P.Type.PUBACK])
	assert_eq(parser.buffered_bytes(), 3, "partial packet kept")
	parser.feed(last.slice(3))
	assert_eq(parser.next().payload, PackedByteArray([7, 8]))


func test_stream_parser_reports_malformed_stream() -> void:
	var parser := MqttStreamParser.new()
	parser.feed(PackedByteArray([0x30, 0xFF, 0xFF, 0xFF, 0xFF, 0x01]))
	assert_eq(parser.next(), {})
	assert_ne(parser.error, "")


func test_connect_with_user_name_and_password() -> void:
	var packet := P.connect_packet("c", 30, {}, "godot", "pw")
	assert_eq(packet[9], 0x02 | 0x80 | 0x40, "clean session + user name + password flags")
	var body: PackedByteArray = P.decode(packet).body
	assert_eq(body.slice(10), PackedByteArray([0, 1, 99, 0, 5]) + "godot".to_utf8_buffer()
		+ PackedByteArray([0, 2]) + "pw".to_utf8_buffer())
	assert_eq(P.connect_packet("c", 30, {}, "u")[9], 0x02 | 0x80, "user name without password")
