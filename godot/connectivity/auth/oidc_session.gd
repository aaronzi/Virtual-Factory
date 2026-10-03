class_name OidcSession
extends Node
## Login of the training UI at the realm's token endpoint (secure profile, ADR-0027): OAuth 2.0 password
## grant of a training user with the public client `vf-godot` (no secret in the app), refresh before the
## access token expires (refresh token, else a new password grant), the token goes to HttpJson.bearer_token
## so every REST client of the UI sends it.
## Why the password grant: a desktop/XR training app with known local training users needs no browser
## redirect or loopback listener; the device authorization grant (enabled on the client) is the production
## path for headsets, the authorization code flow + PKCE for desktop builds with a browser (security.md).

signal logged_in(user: String, roles: Array)
signal login_failed(reason: String)

const RETRY_S := 10.0

var token_url := ""
var client_id := "vf-godot"
var user := ""
var roles: Array = []
var _password := ""
var _refresh_token := ""
var _timer: Timer


func _ready() -> void:
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.timeout.connect(_renew)
	add_child(_timer)


## Password grant; true when logged in (the token is renewed in the background afterwards).
func login(p_user: String, p_password: String) -> bool:
	user = p_user
	_password = p_password
	return await _grant({"grant_type": "password", "username": user, "password": _password})


func logout() -> void:
	HttpJson.bearer_token = ""
	_refresh_token = ""
	roles = []
	if _timer:
		_timer.stop()


func is_logged_in() -> bool:
	return HttpJson.bearer_token != ""


func _renew() -> void:
	var ok := false
	if _refresh_token != "":
		ok = await _grant({"grant_type": "refresh_token", "refresh_token": _refresh_token})
	if not ok:
		ok = await _grant({"grant_type": "password", "username": user, "password": _password})
	if not ok:
		_timer.start(RETRY_S)


func _grant(form: Dictionary) -> bool:
	form["client_id"] = client_id
	var http := HTTPRequest.new()
	http.timeout = 10.0
	add_child(http)
	var headers := PackedStringArray(["Content-Type: application/x-www-form-urlencoded",
		"Accept: application/json"])
	if http.request(token_url, headers, HTTPClient.METHOD_POST, form_encode(form)) != OK:
		http.queue_free()
		return _failed("cannot reach " + token_url)
	var result: Array = await http.request_completed
	http.queue_free()
	var data: Variant = JSON.parse_string(PackedByteArray(result[3]).get_string_from_utf8())
	if result[0] != HTTPRequest.RESULT_SUCCESS or result[1] != 200 or not data is Dictionary:
		var reason: String = data.get("error_description", "HTTP %d" % result[1]) if data is Dictionary \
			else "HTTP %d" % result[1]
		return _failed(reason)
	return _accept(data)


func _accept(data: Dictionary) -> bool:
	HttpJson.bearer_token = data.get("access_token", "")
	_refresh_token = data.get("refresh_token", "")
	roles = token_roles(HttpJson.bearer_token)
	_timer.start(maxf(float(data.get("expires_in", 300)) * 0.8, 5.0))
	logged_in.emit(user, roles)
	return HttpJson.bearer_token != ""


func _failed(reason: String) -> bool:
	push_warning("OIDC: login of '%s' failed: %s" % [user, reason])
	login_failed.emit(reason)
	return false


## application/x-www-form-urlencoded body.
static func form_encode(form: Dictionary) -> String:
	var parts := PackedStringArray()
	for key: String in form:
		parts.append("%s=%s" % [key.uri_encode(), str(form[key]).uri_encode()])
	return "&".join(parts)


## Realm roles of an access token (payload claim realm_access.roles; not verified - display only).
static func token_roles(token: String) -> Array:
	var parts := token.split(".")
	if parts.size() < 2:
		return []
	var b64 := parts[1].replace("-", "+").replace("_", "/")
	b64 += "=".repeat((4 - b64.length() % 4) % 4)
	var claims: Variant = JSON.parse_string(Marshalls.base64_to_utf8(b64))
	if not claims is Dictionary:
		return []
	return (claims.get("realm_access", {}) as Dictionary).get("roles", [])
