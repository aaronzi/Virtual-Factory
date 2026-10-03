class_name AasClient
extends HttpJson
## Read access to the AAS server (AAS Part 2 HTTP API) for the in-world AAS inspector.

var base_url := "http://localhost:8091"
var id_base := "https://virtual-factory.example/ids"
var _units := {}  # concept id -> unit


func aas_id(tag: String) -> String:
	return "%s/aas/%s" % [id_base, tag]


## AAS tag of a workpiece serial (PC3280-2026-000123 -> WP_PC3280_2026_000123).
static func workpiece_tag(serial: String) -> String:
	return "WP_" + serial.replace("-", "_")


func get_shell(id: String) -> Dictionary:
	var r := await request("%s/shells/%s" % [base_url, b64url(id)])
	return r.data if r.ok and r.data is Dictionary else {}


func get_submodel(id: String) -> Dictionary:
	var r := await request("%s/submodels/%s" % [base_url, b64url(id)])
	return r.data if r.ok and r.data is Dictionary else {}


## Unit of a concept description (IEC 61360), "" if none; cached because many elements share concepts.
func get_unit(concept_id: String) -> String:
	if _units.has(concept_id):
		return _units[concept_id]
	var r := await request("%s/concept-descriptions/%s" % [base_url, b64url(concept_id)])
	var unit := ""
	if r.ok and r.data is Dictionary:
		for spec: Dictionary in r.data.get("embeddedDataSpecifications", []):
			unit = String(spec.get("dataSpecificationContent", {}).get("unit", ""))
	_units[concept_id] = unit
	return unit


## The shell's default thumbnail as an Image, or null.
func get_thumbnail(id: String) -> Image:
	var r := await request("%s/shells/%s/asset-information/thumbnail" % [base_url, b64url(id)])
	if not r.ok or r.body.is_empty():
		return null
	var image := Image.new()
	var err := image.load_png_from_buffer(r.body)
	if err != OK:
		err = image.load_jpg_from_buffer(r.body)
	return image if err == OK else null


## Synchronous operation invocation; inputs {idShort: value} of Property variables, returns {idShort: value}.
func invoke(submodel_id: String, path: String, inputs: Dictionary) -> Dictionary:
	var args := []
	for key: String in inputs:
		var v: Variant = inputs[key]
		var value_type := "xs:boolean" if v is bool else "xs:int" if v is int else "xs:string"
		args.append({"value": {"modelType": "Property", "idShort": key, "valueType": value_type,
			"value": str(v).to_lower() if v is bool else str(v)}})
	var url := "%s/submodels/%s/submodel-elements/%s/invoke" % [base_url, b64url(submodel_id), path]
	var r := await request(url, HTTPClient.METHOD_POST, {"inputArguments": args,
		"clientTimeoutDuration": "PT15S"})
	var out := {"ok": r.ok}
	if r.ok and r.data is Dictionary:
		for arg: Dictionary in r.data.get("outputArguments", []):
			out[arg.value.idShort] = arg.value.get("value")
	return out
