extends GutTest
## Inspector action of workpieces: "scan" the QR code - the Digital Link opens on the GS1 resolver.

const LINK := "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000123"


func test_workpieces_scan_their_digital_link_on_the_resolver() -> void:
	var ui := TrainingUi.new()
	ui.aas = AasClient.new()
	ui.config = {"resolver_url": "http://localhost:8096/"}
	assert_eq(ui.passport_url(LINK), "http://localhost:8096/01/04099999032808/21/PC3280-2026-000123")
	assert_eq(ui._actions_for("WP_PC3280_2026_000123")[0].id, "scan_qr")
	assert_eq(ui._actions_for("CV01"), [], "no actions for other assets")
	ui.aas.free()
	ui.free()


func test_picked_assets_are_identified_by_their_global_asset_id() -> void:
	var ui := TrainingUi.new()
	ui.aas = AasClient.new()
	assert_eq(ui.asset_id_for("WP_PC3280_2026_000123"), LINK)
	assert_eq(ui.asset_id_for("PC3280-2026-000123"), LINK)
	assert_eq(ui.asset_id_for("CV01"), "https://virtual-factory.example/ids/asset/CV01")
	assert_eq(ui.asset_id_for(LINK), LINK)
	ui.aas.free()
	ui.free()
