class_name AasInspectorView
extends PanelContainer
## In-world AAS inspector (view only): shell header with thumbnail, submodel list and element tree with live
## values. Data is pushed in by a controller (factory); the view only emits user intentions.

signal submodel_selected(submodel_id: String)
signal type_requested(aas_id: String)
signal action_pressed(action_id: String)
signal close_requested

var lang := "en"
var units := {}  # semantic id -> unit (from concept descriptions, filled by the controller)
var _title: Label
var _subtitle: Label
var _live: Label
var _status: Label
var _thumb: TextureRect
var _type_button: Button
var _submodels: ItemList
var _tree: Tree
var _actions: HBoxContainer
var _derived_from := ""
var _submodel_ids: Array[String] = []
var _collapsed := {}  # element path -> true
var _live_fade := 0.0


func _init() -> void:
	theme = UiTheme.get_theme()
	var root := VBoxContainer.new()
	add_child(root)
	root.add_child(_header())
	var body := HSplitContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_submodels = ItemList.new()
	_submodels.custom_minimum_size = Vector2(300, 120)
	_submodels.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_submodels.item_selected.connect(func(i: int) -> void: submodel_selected.emit(_submodel_ids[i]))
	body.add_child(_submodels)
	_tree = Tree.new()
	_tree.columns = 2
	_tree.hide_root = true
	_tree.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.custom_minimum_size.y = 120
	for col in 2:
		_tree.set_column_expand(col, true)
		_tree.set_column_clip_content(col, true)
		_tree.set_column_custom_minimum_width(col, 180)
	_tree.set_column_expand_ratio(1, 2)
	_tree.item_collapsed.connect(_on_collapsed)
	body.add_child(_tree)
	root.add_child(body)
	_actions = HBoxContainer.new()
	root.add_child(_actions)
	_status = UiTheme.label("", 18, UiTheme.MUTED)
	root.add_child(_status)


func _process(delta: float) -> void:
	if _live_fade > 0.0:
		_live_fade = maxf(_live_fade - delta, 0.0)
		_live.modulate.a = 0.35 + 0.65 * _live_fade


func show_shell(shell: Dictionary) -> void:
	_title.text = AasFormat.display_name(shell, lang)
	var info: Dictionary = shell.get("assetInformation", {})
	_subtitle.text = "%s · %s" % [info.get("assetKind", ""), info.get("globalAssetId", shell.get("id", ""))]
	_derived_from = ""
	var derived: Dictionary = shell.get("derivedFrom", {})
	if not derived.get("keys", []).is_empty():
		_derived_from = derived.keys[0].value
	_type_button.visible = _derived_from != ""
	_thumb.texture = null
	_tree.clear()
	_submodels.clear()
	_submodel_ids.clear()


func set_thumbnail(image: Image) -> void:
	_thumb.texture = ImageTexture.create_from_image(image) if image else null


## Adds a submodel entry (in the order the controller resolves them).
func add_submodel(submodel: Dictionary) -> void:
	_submodel_ids.append(submodel.get("id", ""))
	_submodels.add_item(AasFormat.display_name(submodel, lang))


func select_submodel(submodel_id: String) -> void:
	var i := _submodel_ids.find(submodel_id)
	if i >= 0:
		_submodels.select(i)


## Shows (or refreshes, keeping the collapsed state) the element tree of a submodel.
func show_submodel(submodel: Dictionary) -> void:
	var scroll := _tree.get_scroll()
	_tree.clear()
	var root := _tree.create_item()
	for element: Dictionary in submodel.get("submodelElements", []):
		_add_element(root, element, element.get("idShort", ""))
	_tree.scroll_to_item.call_deferred(root)
	_restore_scroll.call_deferred(scroll)


func _restore_scroll(scroll: Vector2) -> void:
	for child in _tree.get_children(true):
		if child is VScrollBar:
			child.value = scroll.y


func flash_live() -> void:
	_live_fade = 1.0


func set_status(text: String) -> void:
	_status.text = text


## Context actions shown under the tree, e.g. [{"id": "exchange", "label": "Exchange KLT"}].
func set_actions(actions: Array) -> void:
	for child in _actions.get_children():
		child.queue_free()
	for a: Dictionary in actions:
		var b := Button.new()
		b.text = a.label
		b.pressed.connect(func() -> void: action_pressed.emit(a.id))
		_actions.add_child(b)


func _add_element(parent: TreeItem, element: Dictionary, path: String) -> void:
	var item := _tree.create_item(parent)
	var name: String = element.get("idShort", "[%d]" % (parent.get_child_count() - 1))
	item.set_text(0, name)
	var unit: String = units.get(AasFormat.semantic_id(element), "")
	item.set_text(1, AasFormat.value_text(element, lang) + (" " + unit if unit != "" else ""))
	item.set_text_alignment(1, HORIZONTAL_ALIGNMENT_LEFT)
	item.set_custom_color(1, UiTheme.ACCENT.lightened(0.35))
	item.set_tooltip_text(0, AasFormat.lang_text(element.get("description"), lang))
	item.set_metadata(0, path)
	var kids := AasFormat.children(element)
	for i in kids.size():
		var child: Dictionary = kids[i]
		_add_element(item, child, "%s.%s" % [path, child.get("idShort", str(i))])
	item.collapsed = kids.size() > 0 and _collapsed.get(path, parent != _tree.get_root())


func _on_collapsed(item: TreeItem) -> void:
	_collapsed[item.get_metadata(0)] = item.collapsed


func _header() -> HBoxContainer:
	var row := HBoxContainer.new()
	_thumb = TextureRect.new()
	_thumb.custom_minimum_size = Vector2(110, 110)
	_thumb.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_thumb.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	row.add_child(_thumb)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title = UiTheme.label("", 30)
	_subtitle = UiTheme.label("", 17, UiTheme.MUTED)
	_subtitle.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_live = UiTheme.label("INSPECTOR_LIVE", 17, UiTheme.OK)
	text.add_child(_title)
	text.add_child(_subtitle)
	text.add_child(_live)
	row.add_child(text)
	_type_button = Button.new()
	_type_button.text = "INSPECTOR_OPEN_TYPE"
	_type_button.pressed.connect(func() -> void: type_requested.emit(_derived_from))
	row.add_child(_type_button)
	var close := Button.new()
	close.text = "✕"
	close.pressed.connect(func() -> void: close_requested.emit())
	row.add_child(close)
	return row
