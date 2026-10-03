class_name SecureProfile
extends RefCounted
## Credentials of the secure compose profile (ADR-0027) for the composition root. Off by default (open
## training profile: anonymous MQTT, no tokens). `--vf-secure` (or VF_SECURE=1) switches on the local
## defaults of res://config/backend.json `secure` (training user operator1, broker account godot, Operaton
## user godot); each value can be overridden:
##   --vf-user= / VF_USER, --vf-password= / VF_PASSWORD           training user (OIDC password grant)
##   --vf-uns-user= / VF_UNS_USER, --vf-uns-password= / VF_UNS_PASSWORD   broker account (UNS + AAS events)
##   --vf-bpmn-user= / VF_BPMN_USER, --vf-bpmn-password= / VF_BPMN_PASSWORD   Operaton user (task terminal)

const BACKEND := "res://config/backend.json"

var defaults := {}


func _init(config: Dictionary = {}) -> void:
	var cfg := config if not config.is_empty() else _load(BACKEND)
	if _flag(DevTools.get_arg("vf-secure", OS.get_environment("VF_SECURE"))):
		defaults = cfg.get("secure", {})


## CLI argument > environment variable > secure default > "".
func value(key: String, arg: String, env: String) -> String:
	var v := DevTools.get_arg(arg, OS.get_environment(env))
	return v if v != "" else str(defaults.get(key, ""))


func token_url() -> String:
	return value("token_url", "vf-token-url", "VF_TOKEN_URL")


## Applies the broker account to an MQTT client (no-op without one).
func apply_mqtt(client: MqttClient) -> void:
	client.username = value("mqtt_user", "vf-uns-user", "VF_UNS_USER")
	client.password = value("mqtt_password", "vf-uns-password", "VF_UNS_PASSWORD")


## "Basic ..." header value for the Operaton REST API, "" without a BPMN user.
func bpmn_authorization() -> String:
	var bpmn_user := value("bpmn_user", "vf-bpmn-user", "VF_BPMN_USER")
	if bpmn_user == "":
		return ""
	var pair := "%s:%s" % [bpmn_user, value("bpmn_password", "vf-bpmn-password", "VF_BPMN_PASSWORD")]
	return "Basic " + Marshalls.utf8_to_base64(pair)


## Logs the training user in (background) when a user is configured; null in the open profile.
func start_login(parent: Node) -> OidcSession:
	var login_user := value("user", "vf-user", "VF_USER")
	if login_user == "" or token_url() == "":
		return null
	var session := OidcSession.new()
	session.token_url = token_url()
	session.client_id = str(defaults.get("client_id", "vf-godot"))
	parent.add_child(session)
	session.logged_in.connect(func(u: String, r: Array) -> void:
		print("OIDC: logged in as %s %s" % [u, r]))
	session.login(login_user, value("password", "vf-password", "VF_PASSWORD"))
	return session


static func _flag(text: String) -> bool:
	return text.to_lower() not in ["", "0", "off", "false", "no"]


static func _load(path: String) -> Dictionary:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}
