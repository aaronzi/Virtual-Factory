class_name Fmi3ModelDescription
extends RefCounted
## Parsed FMI 3.0 modelDescription.xml (Co-Simulation subset, see ADR-0002).

var model_name := ""
var description := ""
var instantiation_token := ""
var model_identifier := ""
var default_step_size := 0.0
var variables: Array[Fmi3Variable] = []
var _by_name := {}
var _by_vr := {}


static func load_file(path: String) -> Fmi3ModelDescription:
	var parser := XMLParser.new()
	var err := parser.open(path)
	if err != OK:
		push_error("Cannot open model description %s: %s" % [path, error_string(err)])
		return null
	var md := Fmi3ModelDescription.new()
	var current: Fmi3Variable = null
	while parser.read() == OK:
		if parser.get_node_type() != XMLParser.NODE_ELEMENT:
			continue
		var tag := parser.get_node_name()
		if Fmi3.VAR_TYPES.has(tag):
			current = md._read_variable(parser, Fmi3.VAR_TYPES[tag])
		elif tag == "Start" and current != null and current.type == Fmi3.VarType.STRING:
			current.start = parser.get_named_attribute_value_safe("value")
		else:
			md._read_header_element(parser, tag)
	return md


func get_variable(var_name: String) -> Fmi3Variable:
	return _by_name.get(var_name)


func get_variable_by_vr(vr: int) -> Fmi3Variable:
	return _by_vr.get(vr)


func has_variable(var_name: String) -> bool:
	return _by_name.has(var_name)


func _read_header_element(parser: XMLParser, tag: String) -> void:
	match tag:
		"fmiModelDescription":
			model_name = parser.get_named_attribute_value_safe("modelName")
			description = parser.get_named_attribute_value_safe("description")
			instantiation_token = parser.get_named_attribute_value_safe("instantiationToken")
		"CoSimulation":
			model_identifier = parser.get_named_attribute_value_safe("modelIdentifier")
		"DefaultExperiment":
			default_step_size = parser.get_named_attribute_value_safe("stepSize").to_float()


func _read_variable(parser: XMLParser, type: int) -> Fmi3Variable:
	var v := Fmi3Variable.new()
	v.type = type
	v.name = parser.get_named_attribute_value_safe("name")
	v.value_reference = parser.get_named_attribute_value_safe("valueReference").to_int()
	v.causality = Fmi3.CAUSALITIES.get(
		parser.get_named_attribute_value_safe("causality"), Fmi3.Causality.LOCAL)
	v.variability = Fmi3.VARIABILITIES.get(parser.get_named_attribute_value_safe("variability"),
		Fmi3.Variability.CONTINUOUS if type == Fmi3.VarType.FLOAT64 else Fmi3.Variability.DISCRETE)
	v.unit = parser.get_named_attribute_value_safe("unit")
	v.description = parser.get_named_attribute_value_safe("description")
	var start_text := parser.get_named_attribute_value_safe("start")
	v.start = Fmi3.parse_value(type, start_text) if start_text != "" else Fmi3.default_value(type)
	variables.append(v)
	_by_name[v.name] = v
	_by_vr[v.value_reference] = v
	return v
