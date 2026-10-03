"""Quality verdict of a workpiece against the acceptance limits of the master recipe (formula parameters):
leak rate and stroke time reported by the assembly cell, cap colour measured by QS01. The line itself sorts by
colour only (PLC); the MES verdict covers all characteristics, so a part with a failed cell test that the PLC
packed as good is flagged as mis-sorted (BPMN user task)."""

from __future__ import annotations

from dataclasses import dataclass

D65 = (0.95047, 1.0, 1.08883)


@dataclass(frozen=True)
class Limits:
    leak_rate_max: float = 1.0
    stroke_time_min: float = 0.28
    stroke_time_max: float = 0.36
    delta_e_max: float = 25.0

    @classmethod
    def from_recipe(cls, recipe_values: dict) -> "Limits":
        params = {p["ParameterId"]: p for p in recipe_values["Formula"]["Parameters"]["Parameter"]}
        return cls(leak_rate_max=float(params["LeakRateMax"]["UpperLimit"]),
                   stroke_time_min=float(params["StrokeTime"]["LowerLimit"]),
                   stroke_time_max=float(params["StrokeTime"]["UpperLimit"]),
                   delta_e_max=float(params["DeltaEMax"]["UpperLimit"]))


@dataclass(frozen=True)
class Verdict:
    leak_ok: bool
    stroke_ok: bool
    colour_ok: bool
    lab_text: str
    limits: Limits

    @property
    def passed(self) -> bool:
        return self.leak_ok and self.stroke_ok and self.colour_ok

    @property
    def planned_container(self) -> int:
        return 1 if self.passed else 2

    def apply(self, values: dict, spec: dict, v: dict) -> None:
        """Fills QualityInspection and the two MeasurementValue submodels of the workpiece spec."""
        values["OverallResult"] = "Pass" if self.passed else "Fail"
        values["Disposition"] = "Accepted" if self.passed else "Rejected"
        values["DecisionTime"] = v["inspectedAt"]
        values["Destination"] = {"ref": "aas:KLTA01" if self.passed else "aas:KLTB01"}
        chars = {c["_idShort"]: c for c in values["Characteristics"]["Characteristic"]}
        _characteristic(chars["LeakRate"], round(float(v["leakRate"]), 2), self.leak_ok)
        _characteristic(chars["StrokeTime"], round(float(v["strokeTime"]), 3), self.stroke_ok)
        _characteristic(chars["CapColour"], round(float(v["deltaE"]), 1), self.colour_ok, v["inspectedAt"])
        chars["CapColour"]["MeasuredValueText"] = f"{self.lab_text} (reference L* 42.3, a* 64.4, b* 46.6)"
        for sm in spec["submodels"]:
            if sm.get("idShort") == "MeasurementValue_LeakRate":
                sm["values"]["MeasuredValue"]["Value"] = round(float(v["leakRate"]), 2)
            elif sm.get("idShort") == "MeasurementValue_CapColour":
                sm["values"]["MeasuredValue"]["Value"] = round(float(v["deltaE"]), 1)
                sm["values"]["MeasurementTimestamp"] = v["inspectedAt"]


def evaluate(v: dict, limits: Limits) -> Verdict:
    leak, stroke, delta_e = float(v["leakRate"]), float(v["strokeTime"]), float(v["deltaE"])
    lab = srgb_to_lab(float(v.get("r", 0)), float(v.get("g", 0)), float(v.get("b", 0)))
    return Verdict(leak_ok=leak <= limits.leak_rate_max,
                   stroke_ok=limits.stroke_time_min <= stroke <= limits.stroke_time_max,
                   colour_ok=delta_e <= limits.delta_e_max,
                   lab_text="L* %.1f, a* %.1f, b* %.1f" % lab, limits=limits)


def srgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB (0..1) -> CIE 1976 L*a*b* (D65, 2° observer)."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    x = 0.4124564 * lin[0] + 0.3575761 * lin[1] + 0.1804375 * lin[2]
    y = 0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]
    z = 0.0193339 * lin[0] + 0.1191920 * lin[1] + 0.9503041 * lin[2]
    f = [t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
         for t in (x / D65[0], y / D65[1], z / D65[2])]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def _characteristic(char: dict, value: float, ok: bool, timestamp: str | None = None) -> None:
    char["MeasuredValue"] = value
    char["Result"] = "Pass" if ok else "Fail"
    if timestamp:
        char["Timestamp"] = timestamp
