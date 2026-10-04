@tool
extends EditorPlugin
## Step 2 of tools/bake_lighting.sh (ADR-0031): Godot exposes LightmapGI baking only through the editor's
## "Bake Lightmaps" action, which needs a RenderingDevice renderer (run the editor with
## --rendering-method forward_plus). With `-- --vf-bake-scene=<scene> --vf-bake-output=<file>.lmbake` this
## plugin opens the scene, selects its LightmapGI, triggers the editor's bake into the given file and quits.
## Without these arguments it does nothing.

var _scene := ""
var _output := ""


func _enter_tree() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--vf-bake-scene="):
			_scene = arg.get_slice("=", 1)
		elif arg.begins_with("--vf-bake-output="):
			_output = arg.get_slice("=", 1)
	if _scene != "" and _output != "":
		_bake.call_deferred()


func _bake() -> void:
	var fs := EditorInterface.get_resource_filesystem()
	await get_tree().create_timer(1.0).timeout
	while fs.is_scanning():  # the bake re-imports its textures; not allowed during the startup scan
		await get_tree().create_timer(0.5).timeout
	await get_tree().create_timer(1.0).timeout
	print("[LightmapBake] renderer=%s scene=%s" % [RenderingServer.get_current_rendering_method(), _scene])
	EditorInterface.open_scene_from_path(_scene)
	await get_tree().process_frame
	var gi: LightmapGI
	for node in EditorInterface.get_edited_scene_root().get_children():
		if node is LightmapGI:
			gi = node
	var dialog := _bake_dialog() if gi else null
	if dialog == null:
		push_error("[LightmapBake] no LightmapGI or bake action (Forward+/Mobile renderer required)")
		get_tree().quit(1)
		return
	EditorInterface.edit_node(gi)
	await get_tree().process_frame
	var started := Time.get_ticks_msec()
	dialog.file_selected.emit(_output)  # same entry point as choosing the file after "Bake Lightmaps"
	var ok := gi.light_data != null and gi.light_data.get_user_count() > 0
	print("[LightmapBake] %s: %d users in %.1f s" % ["done" if ok else "FAILED",
		gi.light_data.get_user_count() if gi.light_data else 0, (Time.get_ticks_msec() - started) / 1000.0])
	await get_tree().create_timer(1.0).timeout
	get_tree().quit(0 if ok else 1)


## The LightmapGI editor plugin's save dialog; its file_selected signal starts the bake.
func _bake_dialog() -> EditorFileDialog:
	for dialog: EditorFileDialog in get_tree().root.find_children("*", "EditorFileDialog", true, false):
		if Array(dialog.filters).any(func(f: String) -> bool: return f.contains("*.lmbake")):
			return dialog
	return null
