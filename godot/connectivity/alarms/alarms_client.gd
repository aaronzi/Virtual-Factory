class_name AlarmsClient
extends HttpJson
## REST client of the alarms service (ISA-18.2 alarm management, services/alarms, ADR-0026) for the HMI:
## number of unacknowledged alarms and acknowledge all. Unreachable service -> unacknowledged() = -1.

var base_url := "http://localhost:8099"


func _init() -> void:
	timeout_s = 3.0


## Unacknowledged alarms (states UNACK and RTNUN), -1 if the service is not reachable.
func unacknowledged() -> int:
	var r := await request(base_url + "/api/alarms")
	if not r.ok or not r.data is Array:
		return -1
	var n := 0
	for alarm: Variant in r.data:
		if alarm is Dictionary and alarm.get("state", "") in ["UNACK", "RTNUN"]:
			n += 1
	return n


## Acknowledges every unacknowledged alarm as `operator`; true on success.
func ack_all(operator: String) -> bool:
	var r := await request(base_url + "/api/alarms/ack", HTTPClient.METHOD_POST, {"operator": operator})
	return r.ok
