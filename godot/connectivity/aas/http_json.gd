class_name HttpJson
extends Node
## Minimal async JSON over HTTP for the in-world UI (one HTTPRequest per call, freed afterwards).
## `await request(...)` returns {"ok": bool, "status": int, "data": Variant, "body": PackedByteArray}.

@export var timeout_s := 10.0


func request(url: String, method := HTTPClient.METHOD_GET, body: Variant = null) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = timeout_s
	add_child(http)
	var headers := PackedStringArray(["Accept: application/json"])
	var payload := ""
	if body != null:
		headers.append("Content-Type: application/json")
		payload = JSON.stringify(body)
	var err := http.request(url, headers, method, payload)
	if err != OK:
		http.queue_free()
		return {"ok": false, "status": 0, "data": null, "body": PackedByteArray()}
	var result: Array = await http.request_completed
	http.queue_free()
	var status: int = result[1]
	var raw: PackedByteArray = result[3]
	var data: Variant = JSON.parse_string(raw.get_string_from_utf8()) if raw.size() > 0 else null
	return {"ok": result[0] == HTTPRequest.RESULT_SUCCESS and status < 300, "status": status, "data": data,
		"body": raw}


## Identifier encoding of the AAS HTTP API: base64url without padding.
static func b64url(identifier: String) -> String:
	return Marshalls.utf8_to_base64(identifier).replace("+", "-").replace("/", "_").trim_suffix("=") \
		.trim_suffix("=")
