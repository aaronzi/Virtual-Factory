"""AssetLocation values from the line layout (positions in the hall's local coordinate system)."""

from __future__ import annotations

import datetime as dt

# Hall local coordinate system (LCS): origin = hall floor centre, X = Godot x (material flow),
# Y = -Godot z (towards the back wall), Z = up. Ground control point: fictional site coordinates.
HALL_LCS = {"CoordinateSystemName": "Hall 1 floor coordinates (metres, Z up)", "CoordinateSystemId": "PLANT01-HALL1",
            "CoordinateSystemType": "Cartesian", "ElevationReference": "FinishedFloorLevel",
            "GroundControlPoints": [{"GeographicCoordinates": {"Longitude": 7.7700, "Latitude": 49.4400},
                                     "RelativeCoordinates": {"X": 0.0, "Y": 0.0}}]}
ADDRESS = {"Street": "Fabrikstraße 1", "ZipCode": "67655", "Citytown": "Kaiserslautern", "NationalCode": "DE",
           "AddressRemarks": "VF Pneumatics GmbH, Plant 01, Hall 1, Final Assembly"}


def godot_to_lcs(p: list[float]) -> tuple[float, float, float]:
    return float(p[0]), float(-p[2]), float(p[1])


def location_values(tag: str, position: list[float] | None, description: str) -> dict:
    values = {"Addresses": [ADDRESS], "CoordinateSystems": [HALL_LCS],
              "AssetLocatingInformation": {"Localizable": False}}
    if position is not None:
        x, y, z = godot_to_lcs(position)
        values["AssetTraces"] = {"LocationRecords": [{
            "CoordinateSystemReference": {"ref": f"sm:{tag}/AssetLocation#CoordinateSystems.0"},
            "Position": {"X": round(x, 3), "Y": round(y, 3), "Z": round(z, 3)},
            "Time": dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc).isoformat(),
            "LocationDescription": {"en": description}}]}
    return values


def layout_positions(layout: dict) -> dict[str, list[float]]:
    pos = {d["id"]: d.get("position", [0, 0, 0]) for d in layout["devices"]}
    for prop in layout.get("props", []):
        name = prop["scene"].rsplit("/", 1)[-1].split(".")[0]
        pos.setdefault(name, prop.get("position", [0, 0, 0]))
    return pos
