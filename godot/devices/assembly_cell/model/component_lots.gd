extends RefCounted
## Component lots staged at the material feeders of the assembly cell (black box, no scene access). A feeder
## container holds parts of one lot; when it is empty the next lot is staged, so every component changes its
## lot after its own number of parts. Lot numbers follow the supplier's format: in-house L<YYWW>-<sequence>,
## die caster Druckguss Pfalz DGP-<cast date>-F/R (one cast lot per day), Dichtungstechnik DTS-<YYMM>-<seq>,
## Normteile Rhein-Neckar NRN-<YY>-<seq>, Kunststofftechnik Westrich KTW-<YY>-<seq>.

## [BoM node of PC3280_TYPE, lot format, first sequence number, parts per lot, parts of the first lot
## consumed before serial 1 (staggers the lot changes)]
const FEEDERS := [
	["Barrel", "L2609-%04d", 418, 120, 85],
	["EndCapFront", "DGP-%s-F", 0, 180, 40],
	["EndCapRear", "DGP-%s-R", 0, 200, 150],
	["PistonRod", "L2609-%04d", 2410, 150, 30],
	["Piston", "L2609-%04d", 3387, 250, 100],
	["SealKit", "DTS-2608-%04d", 1172, 500, 380],
	["ScrewM5x16", "NRN-26-%05d", 33870, 300, 200],
	["CushioningScrew", "L2609-%04d", 5370, 600, 250],
	["ProtectiveCap", "KTW-26-%04d", 910, 400, 320],
]
const FIRST_CAST_DATE := "2026-09-14"


## Lots built into the part with serial number `serial_no`: "<node>=<lot>" separated by ";".
static func lots_for(serial_no: int) -> String:
	var parts := PackedStringArray()
	for feeder: Array in FEEDERS:
		var index := floori(float(serial_no - 1 + feeder[4]) / feeder[3])
		parts.append("%s=%s" % [feeder[0], _lot(feeder, index)])
	return ";".join(parts)


static func _lot(feeder: Array, index: int) -> String:
	if feeder[2] == 0:  # die-cast parts: lot = cast date
		var unix := Time.get_unix_time_from_datetime_string(FIRST_CAST_DATE) + index * 86400
		var day := Time.get_date_dict_from_unix_time(unix)
		return feeder[1] % ("%02d%02d%02d" % [day.year % 100, day.month, day.day])
	return feeder[1] % (feeder[2] + index)
