class_name DeviceTag
extends DeviceView
## Floating device identifier (e.g. "LB02") above the device; position the node in the device scene.


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var label := Label3D.new()
	label.text = device.device_id
	label.pixel_size = 0.0012
	label.font_size = 48
	label.outline_size = 12
	label.modulate = Color(1, 1, 1)
	label.outline_modulate = Color(0.1, 0.15, 0.2)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = false
	add_child(label)
