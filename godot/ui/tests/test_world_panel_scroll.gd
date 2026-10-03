extends GutTest
## Scrolling at the pointer reaches scrollable Controls inside a world panel (not only the scroll handle).


func test_scroll_steps_scroll_the_container_under_the_pointer() -> void:
	var panel := WorldPanel.new()
	panel.size_m = Vector2(0.4, 0.3)
	var scroll := ScrollContainer.new()
	var box := VBoxContainer.new()
	for i in 60:
		var label := Label.new()
		label.text = "row %d" % i
		box.add_child(label)
	scroll.add_child(box)
	panel.set_content(scroll)
	add_child_autofree(panel)
	await wait_process_frames(3)
	var hit := {"position": panel.global_position}
	panel._input.pointer_moved(hit)
	panel._input.pointer_scrolled(hit, Vector2(0, 3))
	await wait_process_frames(2)
	assert_gt(scroll.scroll_vertical, 0, "wheel down scrolls the content")
	var down := scroll.scroll_vertical
	panel._input.pointer_scrolled(hit, Vector2(0, -1))
	await wait_process_frames(2)
	assert_lt(scroll.scroll_vertical, down, "wheel up scrolls back")
