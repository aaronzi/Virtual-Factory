class_name DataFlowController
extends Node
## Feeds the data-flow view with real traffic:
##   UNS event published (Godot)     -> device -> UNS gateway -> broker -> MES -> BPMN engine
##   BaSyx event, device data        -> device -> UNS gateway -> broker -> AIMC bridge -> AAS server
##   BaSyx event, workpiece submodel -> MES -> AAS server
##   PLC command acknowledged        -> AAS server (LineControl operation) -> ops gateway -> broker -> PLC
##   UNS telemetry (all outputs)     -> device -> UNS gateway -> broker -> historian (InfluxDB), round robin
##   BaSyx event, ConditionMonitoring -> historian -> maintenance service (RUL) -> AAS server (ADR-0029)
## Controllers on the OPC UA path (ADR-0024, while their backplane is linked) take the plant route instead:
##   PLC01 -> OPC UA server (plc-comm) -> edge connector -> broker -> ...   (telemetry, events)
##   AAS server -> ops gateway -> OPC UA server (method call) -> PLC01         (commands)

const IT_NODES := {
	"Gateway": [Vector3(-1.9, 2.35, -1.3), "UNS gateway (Godot)"],
	"Broker": [Vector3(-1.1, 2.75, -2.0), "MQTT broker (UNS)"],
	"Bridge": [Vector3(0.1, 3.1, -2.0), "AIMC bridge"],
	"AAS": [Vector3(1.3, 2.75, -2.0), "AAS server (BaSyx Go)"],
	"MES": [Vector3(0.1, 2.4, -2.0), "MES"],
	"BPMN": [Vector3(1.3, 2.05, -2.0), "BPMN engine (Operaton)"],
	"Historian": [Vector3(-1.1, 3.45, -2.0), "Historian (InfluxDB)"],
	"OpsGateway": [Vector3(1.3, 3.45, -2.0), "Ops gateway (Control Component)"],
	"Maintenance": [Vector3(0.1, 3.8, -2.0), "Maintenance (health, RUL)"],
}
const OPCUA_NODES := {
	"PlcComm": [Vector3(-2.6, 2.75, -1.6), "OPC UA server (PLC01 comm module)"],
	"Edge": [Vector3(-2.2, 3.1, -2.0), "Edge connector"],
}
const OPCUA_LINKS := [["PLC01", "PlcComm"], ["PlcComm", "Edge"], ["Edge", "Broker"],
	["OpsGateway", "PlcComm"]]
const LINKS := [["Gateway", "Broker"], ["Broker", "Bridge"], ["Bridge", "AAS"], ["Broker", "MES"],
	["MES", "BPMN"], ["MES", "AAS"], ["Broker", "Historian"],
	["AAS", "OpsGateway"], ["OpsGateway", "Broker"], ["Historian", "Maintenance"], ["Maintenance", "AAS"],
	["Maintenance", "BPMN"]]
const DEVICE_SUBMODELS := ["OperationalData", "EnergyConsumption"]
const DEVICE_RATE_S := 3.0
const TELEMETRY_RATE_S := 0.8

var view: DataFlowView
var _uns: UnsGateway
var _backplanes := {}  # device -> PlcBackplane
var _devices: Array = []
var _last_pulse := {}  # tag -> seconds
var _telemetry_seen := 0
var _telemetry_t := 0.0
var _next_device := 0


func setup(builder: FactoryBuilder, uns: UnsGateway, feed: AasEventFeed, backplanes: Array = []) -> void:
	view = DataFlowView.new()
	view.visible = false
	add_child(view)
	for name: String in IT_NODES:
		view.add_node(name, IT_NODES[name][0], IT_NODES[name][1])
	for id: String in builder.devices:
		_devices.append(id)
		view.add_node(id, (builder.devices[id] as Node3D).global_position + Vector3(0, 1.0, 0))
	view.add_node("PLC01", IT_NODES.Gateway[0])
	for link: Array in LINKS:
		view.add_link(link[0], link[1])
	_setup_opcua(backplanes)
	_uns = uns
	if uns:
		uns.event_published.connect(_on_event)
		uns.command_acked.connect(_on_ack)
	if feed:
		feed.submodel_changed.connect(_on_submodel)


func set_visible(on: bool) -> void:
	view.visible = on


## Telemetry is too frequent to show per message: one packet per interval while samples are flowing.
func _process(delta: float) -> void:
	_telemetry_t += delta
	if not view.visible or _uns == null or _devices.is_empty() or _telemetry_t < TELEMETRY_RATE_S:
		return
	_telemetry_t = 0.0
	var count: int = _uns.stats.telemetry
	if count > _telemetry_seen:
		var device: String = _devices[_next_device % _devices.size()]
		_next_device += 1
		view.pulse(_route(device) + ["Historian"], Color(0.75, 0.55, 1.0))
	_telemetry_seen = count


## Line commands reach the PLC only via the LineControl operations (delegated to the ops gateway).
func _on_ack(ack_topic: String, _ack: Dictionary) -> void:
	if "/plc01/cmd-resp/" in ack_topic:
		view.pulse(["AAS", "OpsGateway", "Broker", "Gateway", "PLC01"], Color(1.0, 0.9, 0.3))


func _on_event(device: String, _event: String) -> void:
	view.pulse(_route(device) + ["MES", "BPMN"], Color(1.0, 0.62, 0.15))


## OPC UA method call of the ops gateway, applied by the CPU (backplane write).
func _on_write(_device: String, _accepted: bool) -> void:
	view.pulse(["AAS", "OpsGateway", "PlcComm", "PLC01"], Color(1.0, 0.9, 0.3))


func _setup_opcua(backplanes: Array) -> void:
	if backplanes.is_empty():
		return
	for name: String in OPCUA_NODES:
		view.add_node(name, OPCUA_NODES[name][0], OPCUA_NODES[name][1])
	for link: Array in OPCUA_LINKS:
		view.add_link(link[0], link[1])
	for link: PlcBackplane in backplanes:
		_backplanes[link.device] = link
		link.event_sent.connect(_on_event)
		link.write_applied.connect(_on_write)


## Path of shop-floor data from a device to the broker.
func _route(device: String) -> Array:
	var link: PlcBackplane = _backplanes.get(device)
	if link != null and link.is_linked():
		return [device, "PlcComm", "Edge", "Broker"]
	return [device, "Gateway", "Broker"]


func _on_submodel(submodel_id: String, _type: String) -> void:
	var parts := submodel_id.split("/sm/")
	if parts.size() < 2:
		return
	var path := parts[1].split("/")
	var tag := path[0]
	if tag.begins_with("WP_"):
		view.pulse(["MES", "AAS"], Color(0.35, 0.9, 0.45))
	elif path.size() > 1 and path[1] == "ConditionMonitoring":
		view.pulse(["Historian", "Maintenance", "AAS"], Color(0.95, 0.45, 0.75))
	elif path.size() > 1 and path[1] in DEVICE_SUBMODELS:
		var now := Time.get_ticks_msec() / 1000.0
		if now - float(_last_pulse.get(tag, -100.0)) >= DEVICE_RATE_S:
			_last_pulse[tag] = now
			view.pulse(_route(tag) + ["Bridge", "AAS"], Color(0.3, 0.75, 1.0))
