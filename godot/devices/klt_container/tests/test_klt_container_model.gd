extends GutTest

const Model := preload("res://devices/klt_container/model/klt_container_model.gd")
const MD := "res://devices/klt_container/model/modelDescription.xml"


func test_fill_full_and_exchange() -> void:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("KLT", Fmi3ModelDescription.load_file(MD))
	m.set_value("capacity", 3)
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	m.set_value("item_count_measured", 3)
	m.do_step(0.0, 0.1)
	assert_true(m.get_value("full"))
	m.set_value("exchange", true)
	m.do_step(0.1, 0.1)
	m.do_step(0.2, 0.1)
	assert_eq(m.get_value("exchange_count"), 1, "edge-triggered")
