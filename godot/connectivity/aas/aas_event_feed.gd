class_name AasEventFeed
extends RefCounted
## BaSyx Go MQTT eventing (CloudEvents, submodel granularity, ADR-0015/D13): reports which submodel or shell
## changed. Events carry no element values, so listeners fetch the submodel afterwards.

signal submodel_changed(submodel_id: String, event_type: String)
signal shell_changed(aas_id: String, event_type: String)

var client: MqttClient
var events := 0
var _topic := ""


func _init(p_client: MqttClient, topic := "vf/basyx/#") -> void:
	client = p_client
	_topic = topic
	client.message_received.connect(_on_message)


func start(url: String) -> Error:
	client.subscribe(_topic, 0)
	return client.connect_to_broker(url)


func poll() -> void:
	client.poll()


func stop() -> void:
	client.disconnect_from_broker()


func _on_message(topic: String, payload: PackedByteArray) -> void:
	var event: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not event is Dictionary:
		return
	events += 1
	var type: String = event.get("type", "")
	var data: Dictionary = event.get("data", {}) if event.get("data") is Dictionary else {}
	if "submodel" in topic and data.has("submodelId"):
		submodel_changed.emit(data.submodelId, type)
	elif event.has("subject"):
		if "submodel" in topic:
			submodel_changed.emit(event.subject, type)
		elif "shell" in topic:
			shell_changed.emit(event.subject, type)
