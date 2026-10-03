class_name EnergyMeter
extends RefCounted
## Integrates electrical power into energy (kWh) and powered-on time into operating hours.

var energy_kwh := 0.0
var operating_hours := 0.0


func integrate(power_w: float, h: float, operating := true) -> void:
	energy_kwh += power_w * h / 3.6e6
	if operating:
		operating_hours += h / 3600.0


func save() -> Dictionary:
	return {"energy_kwh": energy_kwh, "operating_hours": operating_hours}


func load(state: Dictionary) -> void:
	energy_kwh = state.get("energy_kwh", 0.0)
	operating_hours = state.get("operating_hours", 0.0)
