class_name Fmi3Variable
extends RefCounted
## One entry of <ModelVariables> in an FMI 3.0 modelDescription.xml.

var name := ""
var value_reference := 0
var type := Fmi3.VarType.FLOAT64
var causality := Fmi3.Causality.LOCAL
var variability := Fmi3.Variability.CONTINUOUS
var start: Variant = null
var unit := ""
var description := ""


func is_settable_before_init() -> bool:
	return causality in [Fmi3.Causality.INPUT, Fmi3.Causality.PARAMETER,
		Fmi3.Causality.STRUCTURAL_PARAMETER]


func is_settable_in_step_mode() -> bool:
	return causality == Fmi3.Causality.INPUT or (
		causality == Fmi3.Causality.PARAMETER and variability == Fmi3.Variability.TUNABLE)


func is_output() -> bool:
	return causality == Fmi3.Causality.OUTPUT
