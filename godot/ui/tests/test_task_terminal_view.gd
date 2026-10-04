extends GutTest
## MES terminal: long task details scroll, long text values get a wrapped multi-line field.


func test_details_are_scrollable_and_long_values_wrap() -> void:
	var view: TaskTerminalView = autofree(TaskTerminalView.new())
	var long_text := "10 Secure the robot cell (Maintenance mode, door open). 20 Replace both finger pads."
	watch_signals(view)
	view.show_task({"id": "t1", "name": "Plan maintenance"}, "Lorem ipsum ".repeat(80),
		{"summary": {"type": "String", "value": "short"}, "instructions": {"type": "String", "value": long_text},
		"partsReplaced": {"type": "Boolean", "value": true}})
	assert_eq(view.find_children("*", "ScrollContainer", true, false).size(), 1, "detail column scrolls")
	var edits := view.find_children("*", "TextEdit", true, false)
	assert_eq(edits.size(), 1, "only the long value gets a multi-line field")
	assert_eq((edits[0] as TextEdit).text, long_text)
	view._on_complete()
	var values: Dictionary = get_signal_parameters(view, "complete_pressed")[1]
	assert_eq(values, {"summary": "short", "instructions": long_text, "partsReplaced": true})
