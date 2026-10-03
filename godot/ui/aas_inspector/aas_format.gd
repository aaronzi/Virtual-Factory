class_name AasFormat
extends RefCounted
## Human-readable text for AAS V3 JSON elements (inspector). Language-aware for multi-language values.


## Text of a LangStringSet in `lang` (fallback: English, then the first entry).
static func lang_text(values: Variant, lang: String) -> String:
	if not values is Array or values.is_empty():
		return ""
	for wanted in [lang, "en"]:
		for entry: Dictionary in values:
			if String(entry.get("language", "")).begins_with(wanted):
				return entry.get("text", "")
	return values[0].get("text", "")


static func display_name(referable: Dictionary, lang: String) -> String:
	var name := lang_text(referable.get("displayName"), lang)
	return name if name != "" else referable.get("idShort", "")


## Children of a collection-like element (SMC, SML, Entity statements, operation variables).
static func children(element: Dictionary) -> Array:
	match element.get("modelType", ""):
		"SubmodelElementCollection", "SubmodelElementList":
			return element.get("value", []) if element.get("value") is Array else []
		"Entity":
			return element.get("statements", [])
		"Operation":
			var out := []
			for field in ["inputVariables", "outputVariables"]:
				for v: Dictionary in element.get(field, []):
					out.append(v.value)
			return out
	return []


static func value_text(element: Dictionary, lang: String) -> String:
	var v: Variant = element.get("value")
	match element.get("modelType", ""):
		"Property":
			return _number(str(v), element.get("valueType", "")) if v != null else ""
		"MultiLanguageProperty":
			return lang_text(v, lang)
		"Range":
			return "%s … %s" % [element.get("min", ""), element.get("max", "")]
		"File", "Blob":
			return "%s (%s)" % [str(v) if v != null and element.modelType == "File" else "",
				element.get("contentType", "")]
		"ReferenceElement":
			return _reference(v)
		"RelationshipElement":
			return "%s → %s" % [_reference(element.get("first")), _reference(element.get("second"))]
		"Entity":
			return element.get("globalAssetId", element.get("entityType", ""))
		"Operation":
			return "operation"
		"SubmodelElementList", "SubmodelElementCollection":
			return "[%d]" % children(element).size()
	return ""


static func _reference(ref: Variant) -> String:
	if not ref is Dictionary or ref.get("keys", []).is_empty():
		return ""
	var keys: Array = ref.keys
	var last: String = keys[-1].get("value", "")
	return last.get_file() if keys.size() == 1 else last


## Shortens decimals of floating point values (0.4499999881 -> 0.45).
static func _number(text: String, value_type: String) -> String:
	if value_type not in ["xs:double", "xs:float", "xs:decimal"] or not text.is_valid_float():
		return text
	var f := text.to_float()
	var shown := ("%.4f" % f).rstrip("0").rstrip(".") if absf(f) < 1e6 else text
	return "0" if shown == "-0" else shown
