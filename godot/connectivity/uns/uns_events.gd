class_name UnsEvents
extends RefCounted
## Domain events from `events.definitions`: after each master step, an event fires when its trigger
## variable changed since the previous step (and equals `when`, if given). Field values are read in the
## same tick. Trigger values are sampled at construction, so nothing fires for the initial state.

var definitions: Array[Definition] = []


func _init(master: CoSimMaster, config: UnsConfig) -> void:
	var section := config.section("events")
	var template: String = section.get("topic", "{root}/{device}/event/{event}")
	for raw: Dictionary in section.get("definitions", []):
		var d := _make_definition(master, raw)
		if d == null:
			push_error("UNS: invalid event definition %s" % JSON.stringify(raw))
			continue
		d.topic = config.topic(template, d.device, d.event)
		definitions.append(d)


## Returns [definition, fields Dictionary] for every event that fired in this tick.
func detect() -> Array:
	var fired := []
	for d in definitions:
		var value: Variant = d.trigger_fmu.get_value_by_vr(d.trigger_vr)
		if value == d.last:
			continue
		d.last = value
		if d.has_when and value != d.when:
			continue
		var fields := {}
		for f: Array in d.fields:
			fields[f[0]] = UnsConfig.json_value((f[1] as Fmi3CoSimulation).get_value_by_vr(f[2]))
		fired.append([d, fields])
	return fired


func _make_definition(master: CoSimMaster, raw: Dictionary) -> Definition:
	var trigger := UnsConfig.resolve(master, raw.get("trigger", ""))
	if trigger.is_empty() or not raw.has("event") or not raw.has("device"):
		return null
	var d := Definition.new()
	d.event = raw.event
	d.device = raw.device
	d.trigger_fmu = trigger.fmu
	d.trigger_vr = (trigger.variable as Fmi3Variable).value_reference
	d.last = d.trigger_fmu.get_value_by_vr(d.trigger_vr)
	d.has_when = raw.has("when")
	if d.has_when:
		d.when = Fmi3.coerce((trigger.variable as Fmi3Variable).type, raw.when)
	var fields: Dictionary = raw.get("fields", {})
	for key: String in fields:
		var ep := UnsConfig.resolve(master, fields[key])
		if ep.is_empty():
			return null
		d.fields.append([key, ep.fmu, (ep.variable as Fmi3Variable).value_reference])
	return d


## One configured event.
class Definition:
	var event := ""
	var device := ""
	var topic := ""
	var trigger_fmu: Fmi3CoSimulation
	var trigger_vr := 0
	var has_when := false
	var when: Variant
	var last: Variant
	var fields: Array = []  # [key, fmu, value reference]
