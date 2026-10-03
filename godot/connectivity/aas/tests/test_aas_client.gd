extends GutTest

const DL := "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123"
const AAS := "https://virtual-factory.example/ids/aas/WP_PC3280_2026_000123"
const SM := "https://virtual-factory.example/ids/sm/WP_PC3280_2026_000123/Nameplate/3"


## AAS infrastructure fake: a supplier environment (empty) and the own one; records the requested URLs.
class FakeAas:
	extends AasClient
	var urls := []

	func request(url: String, _method := HTTPClient.METHOD_GET, _body: Variant = null) -> Dictionary:
		urls.append(url)
		var data: Variant = null
		if url.begins_with("http://own/lookup/shells?assetIds="):
			var query: Variant = JSON.parse_string(Marshalls.base64_to_utf8(_pad(url.get_slice("=", 1))))
			data = {"result": [AAS] if query.value == DL else []}
		elif url == "http://own/shell-descriptors/" + b64url(AAS):
			data = {"id": AAS, "endpoints": [_ep("AAS-3.0", "http://repo/shells/x")],
				"submodelDescriptors": [{"id": SM, "endpoints": [_ep("SUBMODEL-3.0", "http://repo/submodels/y")]}]}
		elif url.begins_with("http://repo/"):
			data = {"id": url}
		return {"ok": data != null, "status": 200 if data != null else 404, "data": data, "body": []}

	func request_many(list: Array) -> Array:
		return list.map(func(u: String) -> Dictionary: return request(u))

	static func _ep(interface: String, href: String) -> Dictionary:
		return {"interface": interface, "protocolInformation": {"href": href}}

	static func _pad(s: String) -> String:
		s = s.replace("-", "+").replace("_", "/")
		return s + "=".repeat((4 - s.length() % 4) % 4)


func test_ids() -> void:
	assert_eq(HttpJson.b64url("https://virtual-factory.example/ids/aas/RB01"),
		"aHR0cHM6Ly92aXJ0dWFsLWZhY3RvcnkuZXhhbXBsZS9pZHMvYWFzL1JCMDE")
	assert_eq(AasClient.workpiece_tag("PC3280-2026-000123"), "WP_PC3280_2026_000123")
	var client := AasClient.new()
	assert_eq(client.asset_id("KLTA01"), "https://virtual-factory.example/ids/asset/KLTA01")
	client.free()


func test_asset_id_resolves_via_discovery_and_registry_over_environments() -> void:
	var aas := FakeAas.new()
	add_child_autofree(aas)
	aas.registries = [
		{"name": "supplier", "discovery": "http://sup", "aas_registry": "http://sup",
			"submodel_registry": "http://sup"},
		{"name": "vf", "discovery": "http://own", "aas_registry": "http://own",
			"submodel_registry": "http://own"}]
	assert_eq(await aas.lookup(DL), [AAS])
	assert_eq((await aas.get_shell(AAS)).id, "http://repo/shells/x", "shell from the descriptor endpoint")
	assert_eq((await aas.get_submodel(SM)).id, "http://repo/submodels/y")
	assert_eq(await aas.lookup("urn:unknown"), [])
	var descriptor_calls := aas.urls.filter(func(u: String) -> bool: return "shell-descriptors" in u).size()
	await aas.get_shell(AAS)
	assert_eq(aas.urls.filter(func(u: String) -> bool: return "shell-descriptors" in u).size(), descriptor_calls,
		"endpoint cached")
	aas.forget(AAS)
	await aas.get_shell(AAS)
	assert_gt(aas.urls.filter(func(u: String) -> bool: return "shell-descriptors" in u).size(), descriptor_calls)
	assert_eq(await aas.shell_href("urn:not-registered"),
		"http://localhost:8091/shells/dXJuOm5vdC1yZWdpc3RlcmVk", "documented fallback: own repository")


func test_event_feed_parses_cloud_events() -> void:
	var feed := AasEventFeed.new(MqttClient.new())
	var seen := []
	feed.submodel_changed.connect(func(id: String, type: String) -> void: seen.append([id, type]))
	var event := {"type": "io.admin-shell.submodel.updated.v1", "subject": "urn:sm",
		"data": {"submodelId": "urn:sm"}}
	feed._on_message("vf/basyx/submodelrepository/submodel/updated", JSON.stringify(event).to_utf8_buffer())
	assert_eq(seen, [["urn:sm", "io.admin-shell.submodel.updated.v1"]])
