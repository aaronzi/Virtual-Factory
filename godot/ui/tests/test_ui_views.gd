extends GutTest


func test_aas_format_values() -> void:
	var prop := {"modelType": "Property", "valueType": "xs:double", "value": "0.4499999881"}
	assert_eq(AasFormat.value_text(prop, "en"), "0.45")
	var mlp := {"modelType": "MultiLanguageProperty", "value": [{"language": "en", "text": "Robot"},
		{"language": "de", "text": "Roboter"}]}
	assert_eq(AasFormat.value_text(mlp, "de"), "Roboter")
	assert_eq(AasFormat.value_text(mlp, "fr"), "Robot")
	var ref := {"modelType": "ReferenceElement", "value": {"keys": [
		{"type": "AssetAdministrationShell", "value": "https://x/ids/aas/KLTA01"}]}}
	assert_eq(AasFormat.value_text(ref, "en"), "KLTA01")
	var smc := {"modelType": "SubmodelElementCollection", "value": [prop, prop]}
	assert_eq(AasFormat.children(smc).size(), 2)


func test_inspector_shows_tree() -> void:
	var view := AasInspectorView.new()
	add_child_autofree(view)
	view.show_shell({"idShort": "RB01", "assetInformation": {"assetKind": "Instance"},
		"derivedFrom": {"keys": [{"value": "https://x/ids/aas/UR5E_TYPE"}]}})
	view.show_submodel({"submodelElements": [{"modelType": "Property", "idShort": "OperatingState",
		"valueType": "xs:string", "value": "Busy"}]})
	var item := view._tree.get_root().get_first_child()
	assert_eq(item.get_text(0), "OperatingState")
	assert_eq(item.get_text(1), "Busy")
	assert_true(view._type_button.visible)


func test_world_panel_maps_hits_to_pixels() -> void:
	var panel := WorldPanel.new()
	panel.size_m = Vector2(1.0, 0.5)
	panel.set_content(Control.new())
	add_child_autofree(panel)
	assert_eq(panel.to_viewport(panel.global_position), Vector2(500, 250))
	assert_eq(panel.to_viewport(panel.global_position + Vector3(-0.5, 0.25, 0)), Vector2(0, 0))


func test_hmi_enables_allowed_commands() -> void:
	var view := HmiView.new()
	add_child_autofree(view)
	view.update_status({"state": PackMLStateMachine.State.EXECUTE, "state_name": "EXECUTE", "total": 10,
		"ok": 9, "nok": 1})
	assert_false(view._buttons[PackMLStateMachine.Command.HOLD].disabled)
	assert_true(view._buttons[PackMLStateMachine.Command.START].disabled)


func test_tour_loads_and_moves_rig() -> void:
	var tour := CameraTour.new()
	assert_true(tour.load_tour("res://config/tours/default.json"))
	assert_gt(tour.stops.size(), 3)
