class_name Fmi3
extends RefCounted
## FMI 3.0 enumerations and helpers shared by all co-simulation models (ADR-0002).

enum Status { OK, WARNING, DISCARD, ERROR, FATAL }
enum Causality { PARAMETER, CALCULATED_PARAMETER, INPUT, OUTPUT, LOCAL, INDEPENDENT, STRUCTURAL_PARAMETER }
enum Variability { CONSTANT, FIXED, TUNABLE, DISCRETE, CONTINUOUS }
enum VarType { FLOAT64, INT32, UINT64, BOOLEAN, STRING }

const CAUSALITIES := {
	"parameter": Causality.PARAMETER, "calculatedParameter": Causality.CALCULATED_PARAMETER,
	"input": Causality.INPUT, "output": Causality.OUTPUT, "local": Causality.LOCAL,
	"independent": Causality.INDEPENDENT, "structuralParameter": Causality.STRUCTURAL_PARAMETER,
}
const VARIABILITIES := {
	"constant": Variability.CONSTANT, "fixed": Variability.FIXED, "tunable": Variability.TUNABLE,
	"discrete": Variability.DISCRETE, "continuous": Variability.CONTINUOUS,
}
const VAR_TYPES := {
	"Float64": VarType.FLOAT64, "Int32": VarType.INT32, "UInt64": VarType.UINT64,
	"Boolean": VarType.BOOLEAN, "String": VarType.STRING,
}


## Converts an XML attribute string to the GDScript value of the given FMI type.
static func parse_value(type: int, text: String) -> Variant:
	match type:
		VarType.FLOAT64:
			return text.to_float()
		VarType.INT32, VarType.UINT64:
			return text.to_int()
		VarType.BOOLEAN:
			return text == "true" or text == "1"
		_:
			return text


static func default_value(type: int) -> Variant:
	match type:
		VarType.FLOAT64:
			return 0.0
		VarType.INT32, VarType.UINT64:
			return 0
		VarType.BOOLEAN:
			return false
		_:
			return ""


## Coerces `value` to the GDScript representation of `type` (e.g. int -> float for Float64).
static func coerce(type: int, value: Variant) -> Variant:
	match type:
		VarType.FLOAT64:
			return float(value)
		VarType.INT32, VarType.UINT64:
			return int(value)
		VarType.BOOLEAN:
			return bool(value)
		_:
			return str(value)


static func status_name(status: int) -> String:
	return Status.keys()[status]
