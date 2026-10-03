extends GutTest
## OidcSession helpers and the token hand-over to HttpJson (no identity provider needed).


func after_each() -> void:
	HttpJson.bearer_token = ""


func _token(claims: Dictionary) -> String:
	var payload := Marshalls.utf8_to_base64(JSON.stringify(claims)).replace("+", "-").replace("/", "_")
	return "eyJhbGciOiJSUzI1NiJ9.%s.c2ln" % payload.trim_suffix("=").trim_suffix("=")


func test_form_encoding_escapes_reserved_characters() -> void:
	var body := OidcSession.form_encode({"grant_type": "password", "username": "operator1",
		"password": "a b&c=d"})
	assert_eq(body, "grant_type=password&username=operator1&password=a%20b%26c%3Dd")


func test_roles_are_read_from_the_token_payload() -> void:
	var token := _token({"sub": "x", "realm_access": {"roles": ["operator", "quality"]}})
	assert_eq(OidcSession.token_roles(token), ["operator", "quality"])
	assert_eq(OidcSession.token_roles("not-a-token"), [])


func test_accepted_token_is_sent_by_every_http_client() -> void:
	var session := OidcSession.new()
	add_child_autofree(session)
	watch_signals(session)
	var token := _token({"realm_access": {"roles": ["operator"]}})
	assert_true(session._accept({"access_token": token, "refresh_token": "r", "expires_in": 300}))
	assert_signal_emitted(session, "logged_in")
	var client := HttpJson.new()
	add_child_autofree(client)
	assert_has(client._headers(), "Authorization: Bearer " + token)
	client.authorization = "Basic Z29kb3Q6eA=="
	assert_has(client._headers(), "Authorization: Basic Z29kb3Q6eA==", "own header wins (Operaton)")
	session.logout()
	assert_false(session.is_logged_in())
	var plain := HttpJson.new()
	add_child_autofree(plain)
	assert_eq(plain._headers(), PackedStringArray(["Accept: application/json"]), "open profile")
