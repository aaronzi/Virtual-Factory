extends GutTest

const DevToolsScript := preload("res://core/util/dev_tools.gd")


func test_parses_vf_user_args() -> void:
	var parsed := DevToolsScript._parse_user_args(
		PackedStringArray(["--vf-screenshot=/tmp/a.png", "--vf-flag", "ignored"]))
	assert_eq(parsed.get("vf-screenshot"), "/tmp/a.png")
	assert_eq(parsed.get("vf-flag"), "true")
	assert_false(parsed.has("ignored"))
