extends Node
## Development helpers driven by user command-line arguments (after `--`).
##
##   --vf-screenshot=<abs path.png>   capture the main viewport, then quit
##   --vf-screenshot-delay=<seconds>  wait before capturing (default 2.0)
##   --vf-quit-after=<seconds>        quit after the given wall-clock time
##
## Used by tools/screenshot.sh to produce review screenshots without the editor.

var _args: Dictionary = {}


func _ready() -> void:
	_args = _parse_user_args(OS.get_cmdline_user_args())
	if _args.has("vf-screenshot"):
		var delay := float(_args.get("vf-screenshot-delay", "2.0"))
		_capture_after(delay, String(_args["vf-screenshot"]))
	if _args.has("vf-quit-after"):
		await get_tree().create_timer(float(_args["vf-quit-after"]), true, false, true).timeout
		get_tree().quit()


## Returns the value of a `--vf-<name>=<value>` user argument, or `fallback`.
func get_arg(arg_name: String, fallback: String = "") -> String:
	return String(_args.get(arg_name, fallback))


func _capture_after(delay: float, path: String) -> void:
	await get_tree().create_timer(delay, true, false, true).timeout
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	var err := image.save_png(path)
	if err == OK:
		print("[DevTools] screenshot saved: ", path)
	else:
		push_error("[DevTools] screenshot failed (%s): %s" % [error_string(err), path])
	get_tree().quit()


static func _parse_user_args(raw: PackedStringArray) -> Dictionary:
	var parsed := {}
	for arg in raw:
		if not arg.begins_with("--"):
			continue
		var kv := arg.substr(2).split("=", true, 1)
		parsed[kv[0]] = kv[1] if kv.size() > 1 else "true"
	return parsed
