class_name InspectorController
extends Node
## Connects the AAS inspector view with the AAS server: opens a world panel in front of the player for a
## picked asset, loads shell, thumbnail and submodels, and refreshes the visible submodel when BaSyx reports a
## change for it (MQTT eventing -> fetch, decided in the M4 review). Context actions come from a provider.

const PREFERRED := ["QualityInspection", "OperationalData", "HierarchicalStructures", "LineControl",
	"Nameplate"]
const PREFERRED_KLT := ["HierarchicalStructures", "OperationalData"]
const REFRESH_DELAY_S := 0.4

var aas: AasClient
var feed: AasEventFeed
var rig: PlayerRig
var actions_provider: Callable  ## func(tag: String) -> Array of {id, label}
var action_handler: Callable    ## func(tag: String, action_id: String) -> void
var panel: WorldPanel
var view: AasInspectorView
var current_tag := ""
var _shell_id := ""
var _submodel_id := ""
var _refresh_at := -1.0
var _loading := 0


func setup(p_aas: AasClient, p_feed: AasEventFeed, p_rig: PlayerRig) -> void:
	aas = p_aas
	feed = p_feed
	rig = p_rig
	view = AasInspectorView.new()
	view.submodel_selected.connect(_show_submodel)
	view.type_requested.connect(func(id: String) -> void: open_aas(id))
	view.close_requested.connect(close)
	view.action_pressed.connect(func(id: String) -> void:
		if action_handler.is_valid():
			action_handler.call(current_tag, id))
	panel = WorldPanel.new()
	panel.size_m = Vector2(1.0, 0.68)
	panel.always_on_top = true
	panel.refresh_hz = 2.0
	panel.set_content(view)
	panel.visible = false
	add_child(panel)
	if feed:
		feed.submodel_changed.connect(_on_submodel_changed)
		feed.shell_changed.connect(_on_shell_changed)


func _process(_delta: float) -> void:
	if _refresh_at > 0.0 and Time.get_ticks_msec() / 1000.0 >= _refresh_at:
		_refresh_at = -1.0
		_refresh_submodel()


## Opens the AAS of `tag`; `point` (world) is where the asset was clicked - the panel appears between the
## player and that point, so it never ends up behind the asset.
func open_asset(tag: String, point := Vector3.INF) -> void:
	current_tag = tag
	await open_aas(aas.aas_id(tag), point)


func open_aas(aas_id: String, point := Vector3.INF) -> void:
	_loading += 1
	var ticket := _loading
	var started := Time.get_ticks_msec()
	_place(point)
	panel.visible = true
	view.lang = TranslationServer.get_locale().substr(0, 2)
	view.set_status(tr("INSPECTOR_LOADING"))
	var shell := await aas.get_shell(aas_id)
	if ticket != _loading:
		return
	if shell.is_empty():
		view.show_shell({"idShort": aas_id.get_file()})
		view.set_status(tr("INSPECTOR_NO_AAS") % aas_id)
		return
	_shell_id = aas_id
	current_tag = aas_id.get_file()
	view.show_shell(shell)
	view.set_actions(actions_provider.call(current_tag) if actions_provider.is_valid() else [])
	panel.mark_dirty()
	await _load_submodels(shell, ticket)
	print("[Inspector] %s ready in %d ms" % [current_tag, Time.get_ticks_msec() - started])
	if ticket == _loading:
		view.set_thumbnail(await aas.get_thumbnail(aas_id))
		panel.mark_dirty()


func close() -> void:
	panel.visible = false
	_loading += 1
	_shell_id = ""
	_submodel_id = ""
	current_tag = ""


## Re-evaluates the context actions (e.g. when an exchange task appeared).
func refresh_actions() -> void:
	if panel.visible and actions_provider.is_valid():
		view.set_actions(actions_provider.call(current_tag))


func _load_submodels(shell: Dictionary, ticket: int) -> void:
	var first := ""
	var best := 999
	var ids: Array = shell.get("submodels", []).map(func(ref: Dictionary) -> String: return ref.keys[0].value)
	var submodels := await aas.get_submodels(ids)  # parallel
	if ticket != _loading:
		return
	for sm: Dictionary in submodels:
		view.add_submodel(sm)
		var order := PREFERRED_KLT if current_tag.begins_with("KLT") else PREFERRED
		var rank := order.find(sm.get("idShort", ""))
		if rank >= 0 and rank < best or first == "":
			best = rank if rank >= 0 else best
			first = sm.id
	view.set_status(tr("INSPECTOR_HINT"))
	if first != "":
		view.select_submodel(first)
		_show_submodel(first)


func _show_submodel(submodel_id: String) -> void:
	_submodel_id = submodel_id
	await _refresh_submodel()


func _refresh_submodel() -> void:
	if _submodel_id == "":
		return
	var requested := _submodel_id
	var sm := await aas.get_submodel(requested)
	if requested == _submodel_id and not sm.is_empty():
		view.show_submodel(sm)
		view.flash_live()
		panel.mark_dirty()
		if await _load_units(sm) and requested == _submodel_id:
			view.show_submodel(sm)  # again, now with units
			panel.mark_dirty()


## Fetches the units of the submodel's concepts (cached in the client); true if new units were found.
func _load_units(submodel: Dictionary) -> bool:
	var wanted: Array = AasFormat.value_semantic_ids(submodel.get("submodelElements", [])).keys().filter(
		func(sem: String) -> bool: return not view.units.has(sem))
	if wanted.is_empty():
		return false
	var units := await aas.get_units(wanted)  # parallel, cached
	view.units.merge(units)
	return units.values().any(func(u: String) -> bool: return u != "")


func _on_submodel_changed(submodel_id: String, _type: String) -> void:
	if panel.visible and submodel_id == _submodel_id and _refresh_at < 0.0:
		_refresh_at = Time.get_ticks_msec() / 1000.0 + REFRESH_DELAY_S


func _on_shell_changed(aas_id: String, _type: String) -> void:
	if panel.visible and aas_id == _shell_id:
		open_aas(aas_id)  # e.g. a workpiece got new submodels


func _place(point: Vector3) -> void:
	var cam := rig.get_view_camera()
	var direction := -cam.global_basis.z
	var distance := 1.1
	if point.is_finite():
		direction = (point - cam.global_position).normalized()
		distance = clampf(cam.global_position.distance_to(point) * 0.6, 0.55, 1.1)
	direction.y = clampf(direction.y, -0.35, 0.2)
	panel.global_position = cam.global_position + direction.normalized() * distance + Vector3(0, -0.05, 0)
	panel.scale = Vector3.ONE * (distance / 1.1)  # same apparent size at any distance
	panel.face(cam.global_position)
