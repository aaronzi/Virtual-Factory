extends GutTest
## Desktop menu: the Grafana link (ADR-0022) comes from backend.json and the view only emits a signal.


func test_dashboard_url_from_backend_config() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://config/backend.json"))
	var url := MenuController.dashboard_url(config)
	assert_true(url.begins_with("http://localhost:3002/"), url)
	assert_string_contains(url, "vf-line01-live")


func test_dashboard_url_default_without_config() -> void:
	assert_eq(MenuController.dashboard_url({}), MenuController.GRAFANA_URL)


func test_menu_button_emits_dashboard_request() -> void:
	var menu: MainMenu = add_child_autofree(MainMenu.new())
	watch_signals(menu)
	var buttons := menu.find_children("*", "Button", true, false).filter(
		func(b: Button) -> bool: return b.text == "MENU_DASHBOARD")
	assert_eq(buttons.size(), 1)
	buttons[0].pressed.emit()
	assert_signal_emitted(menu, "dashboard_requested")
