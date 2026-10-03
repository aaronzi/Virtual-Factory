class_name HttpJson
extends Node
## Minimal async JSON over HTTP for the in-world UI (one HTTPRequest per call, freed afterwards).
## `await request(...)` returns {"ok": bool, "status": int, "data": Variant, "body": PackedByteArray}.
## Secure profile (ADR-0027): every request carries `Authorization: Bearer <bearer_token>` (set by the
## OidcSession of the UI), unless the client has its own `authorization` header (e.g. Basic for Operaton).

## Access token of the logged-in user, shared by all clients ("" = open profile, no header).
static var bearer_token := ""

@export var timeout_s := 10.0
## Own Authorization header value of this client (e.g. "Basic ..."); overrides the bearer token.
var authorization := ""


func request(url: String, method := HTTPClient.METHOD_GET, body: Variant = null) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = timeout_s
	add_child(http)
	var headers := _headers()
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
	var data: Variant = _parse(raw)
	return {"ok": result[0] == HTTPRequest.RESULT_SUCCESS and status < 300, "status": status, "data": data,
		"body": raw}


## Several GET requests in parallel; returns the results in the order of `urls`.
func request_many(urls: Array) -> Array:
	var out := []
	out.resize(urls.size())
	var remaining := [urls.size()]  # boxed counter (lambdas capture by value)
	for i in urls.size():
		var http := HTTPRequest.new()
		http.timeout = timeout_s
		add_child(http)
		http.request_completed.connect(func(result: int, status: int, _h: PackedStringArray,
				raw: PackedByteArray) -> void:
			out[i] = {"ok": result == HTTPRequest.RESULT_SUCCESS and status < 300, "status": status,
				"data": _parse(raw), "body": raw}
			remaining[0] -= 1
			http.queue_free())
		if http.request(urls[i], _headers()) != OK:
			out[i] = {"ok": false, "status": 0, "data": null, "body": PackedByteArray()}
			remaining[0] -= 1
			http.queue_free()
	while remaining[0] > 0:
		await get_tree().process_frame
	return out


func _headers() -> PackedStringArray:
	var headers := PackedStringArray(["Accept: application/json"])
	if authorization != "":
		headers.append("Authorization: " + authorization)
	elif bearer_token != "":
		headers.append("Authorization: Bearer " + bearer_token)
	return headers


## JSON body -> Variant; binary bodies (thumbnails, files) -> null without a parse error.
static func _parse(raw: PackedByteArray) -> Variant:
	if raw.is_empty() or not char(raw[0]) in ["{", "[", "\""]:
		return null
	return JSON.parse_string(raw.get_string_from_utf8())


## Identifier encoding of the AAS HTTP API: base64url without padding.
static func b64url(identifier: String) -> String:
	return Marshalls.utf8_to_base64(identifier).replace("+", "-").replace("/", "_").trim_suffix("=") \
		.trim_suffix("=")
