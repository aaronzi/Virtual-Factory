extends GutTest
## Inspector action of workpieces: open the item-level passport in the BaSyx DPP API.


func test_workpieces_offer_the_passport_with_the_encoded_aas_id() -> void:
	var ui := TrainingUi.new()
	ui.aas = AasClient.new()
	ui.config = {"dpp_url": "http://localhost:8093/"}
	assert_eq(ui.passport_url("WP_PC3280_2026_000123"), "http://localhost:8093/v1/dpps/"
		+ "https%3A%2F%2Fvirtual-factory.example%2Fids%2Faas%2FWP_PC3280_2026_000123")
	assert_eq(ui._actions_for("WP_PC3280_2026_000123")[0].id, "open_passport")
	assert_eq(ui._actions_for("CV01"), [], "no actions for other assets")
	ui.aas.free()
	ui.free()
