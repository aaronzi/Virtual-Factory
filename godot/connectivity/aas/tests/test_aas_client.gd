extends GutTest


func test_ids() -> void:
	assert_eq(HttpJson.b64url("https://virtual-factory.example/ids/aas/RB01"),
		"aHR0cHM6Ly92aXJ0dWFsLWZhY3RvcnkuZXhhbXBsZS9pZHMvYWFzL1JCMDE")
	assert_eq(AasClient.workpiece_tag("PC3280-2026-000123"), "WP_PC3280_2026_000123")
	var client := AasClient.new()
	assert_eq(client.aas_id("KLTA01"), "https://virtual-factory.example/ids/aas/KLTA01")
	client.free()


func test_event_feed_parses_cloud_events() -> void:
	var feed := AasEventFeed.new(MqttClient.new())
	var seen := []
	feed.submodel_changed.connect(func(id: String, type: String) -> void: seen.append([id, type]))
	var event := {"type": "io.admin-shell.submodel.updated.v1", "subject": "urn:sm",
		"data": {"submodelId": "urn:sm"}}
	feed._on_message("vf/basyx/submodelrepository/submodel/updated", JSON.stringify(event).to_utf8_buffer())
	assert_eq(seen, [["urn:sm", "io.admin-shell.submodel.updated.v1"]])
