extends SceneTree
## Loads every project script (outside addons/) so parse/compile errors fail the test run, even for
## scripts no test touches. Used by tools/run_godot_tests.sh.


func _initialize() -> void:
	var failures := 0
	var count := 0
	for path in _scripts("res://"):
		count += 1
		if load(path) == null:
			failures += 1
			printerr("compile_all: failed to load ", path)
	print("compile_all: %d scripts, %d failures" % [count, failures])
	quit(1 if failures > 0 else 0)


func _scripts(dir_path: String) -> PackedStringArray:
	var out := PackedStringArray()
	var dir := DirAccess.open(dir_path)
	for sub in dir.get_directories():
		if sub not in ["addons", ".godot"]:
			out.append_array(_scripts(dir_path.path_join(sub)))
	for file in dir.get_files():
		if file.ends_with(".gd"):
			out.append(dir_path.path_join(file))
	return out
