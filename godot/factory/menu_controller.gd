class_name MenuController
extends Node
## Executes the desktop menu: language, quality preset, simulation speed (physics ticks scale with time,
## so the co-simulation step stays 1/60 s), training scenarios (factory.scenarios), demo tour and data-flow
## view, and opens the Grafana dashboard in the browser (backend.json `grafana_url`, ADR-0022).
## Dev args: --vf-lang=de, --vf-quality=0..2, --vf-tour (start the demo tour), --vf-dataflow,
## --vf-grafana-url=<url>.

const TOUR := "res://config/tours/default.json"
const BASE_TICKS := 60
const GRAFANA_URL := "http://localhost:3002/d/vf-line01-live/line01-live"

var ui: TrainingUi
var menu: MainMenu
var tour: CameraTour
var _info_timer := 0.0


func setup(p_ui: TrainingUi) -> void:
	ui = p_ui
	menu = MainMenu.new()
	add_child(menu)
	menu.language_selected.connect(set_language)
	menu.quality_selected.connect(func(p: int) -> void: QualitySettings.apply(ui.get_parent(), p))
	menu.speed_selected.connect(set_speed)
	menu.scenario_start.connect(_start_scenario)
	menu.scenario_stop.connect(_stop_scenario)
	menu.tour_toggled.connect(_toggle_tour)
	menu.dataflow_toggled.connect(func(on: bool) -> void: ui.set_dataflow(on))
	menu.dashboard_requested.connect(func() -> void:
		OS.shell_open(DevTools.get_arg("vf-grafana-url", dashboard_url(ui.config))))
	tour = CameraTour.new()
	tour.rig = ui.rig
	tour.load_tour(TOUR)
	tour.caption_changed.connect(menu.set_caption)
	tour.stop_reached.connect(func(stop: Dictionary) -> void:
		if stop.has("inspect"):
			ui.inspector.open_asset(stop.inspect))
	add_child(tour)
	_refresh_scenarios()
	_apply_dev_args()


func _process(delta: float) -> void:
	_info_timer -= delta
	if _info_timer > 0.0:
		return
	_info_timer = 1.0
	var uns: Variant = ui.factory.get("uns")
	var online := "online" if uns != null and uns.is_broker_connected() else "offline"
	var events: int = ui.feed.events if ui.feed else 0
	var open_tasks: int = ui.tasks.tasks.size() if ui.tasks else 0
	menu.set_info(tr("MENU_INFO") % [online, events, open_tasks])
	menu.show_state(TranslationServer.get_locale(), tour.active)
	var runner: Variant = _runner()
	if runner != null:
		menu.set_scenario_status(tr("SCENARIO_RUNNING") % _scenario_title(runner, runner.active_id)
			if runner.active else tr("SCENARIO_NONE"))


func _toggle_tour(on: bool) -> void:
	if on:
		tour.start()
	else:
		tour.stop()


## Grafana dashboard "LINE01 live" from backend.json `grafana_url` (default: local stack, port 3002).
static func dashboard_url(config: Dictionary) -> String:
	return String(config.get("grafana_url", GRAFANA_URL))


func set_language(locale: String) -> void:
	TranslationServer.set_locale(locale)
	_refresh_scenarios()


func set_speed(factor: float) -> void:
	Engine.physics_ticks_per_second = int(BASE_TICKS * factor)
	Engine.time_scale = factor
	Engine.max_physics_steps_per_frame = maxi(8, int(8 * factor))


func _start_scenario(id: String) -> void:
	var runner: Variant = _runner()
	if runner != null:
		runner.start(id)


func _stop_scenario() -> void:
	var runner: Variant = _runner()
	if runner != null:
		runner.stop()


func _refresh_scenarios() -> void:
	var runner: Variant = _runner()
	menu.set_scenarios(runner.list(_lang()) if runner != null else [])


func _scenario_title(runner: Variant, id: String) -> String:
	for s: Dictionary in runner.list(_lang()):
		if s.id == id:
			return s.title
	return id


static func _lang() -> String:
	return TranslationServer.get_locale().substr(0, 2)


func _runner() -> Variant:
	return ui.factory.get("scenarios")


func _apply_dev_args() -> void:
	var lang := DevTools.get_arg("vf-lang")
	if lang != "":
		set_language(lang)
	var quality := DevTools.get_arg("vf-quality")
	if quality != "":
		QualitySettings.apply(ui.get_parent(), int(quality))
	if DevTools.get_arg("vf-menu") != "":
		menu.open()
	if DevTools.get_arg("vf-dataflow") != "":
		ui.set_dataflow(true)
	if DevTools.get_arg("vf-tour") != "":
		tour.start.call_deferred()
