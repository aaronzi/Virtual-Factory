"""Process data of the executed processes.

OP50/OP60 use the values the assembly cell reports with part_released (leak rate, stroke time from the FMU),
the process BoM the component lots it reports (lots.py). The other black-box cell values (torques, forces,
grease) are not simulated physically: they are generated deterministically per serial number around the
blueprint (= recipe) values. The cell reports the cap it intended to fit; only the inspection at QS01 detects
cap defects.
"""

from __future__ import annotations

import hashlib
import random

from .lots import PROCESS_BOM

MEASURED = {"MeasuredLeakRate", "PressureDecay", "MeasuredStrokeTimeAdvance", "MeasuredStrokeTimeRetract"}


def rng(serial: str) -> random.Random:
    return random.Random(int(hashlib.sha256(serial.encode()).hexdigest()[:12], 16))


def apply(process: dict, op: str, v: dict, r: random.Random, lots: dict[str, str]) -> None:
    for group in ("ProcessParameters", "ResourceParameters"):
        for key, spec in (process.get(group) or {}).items():
            if key.startswith("+") and key[1:] not in MEASURED and spec.get("valueType") == "xs:double":
                spec["value"] = _jitter(spec["value"], r)
    for key, spec in (process.get("ProcessBoM") or {}).items():
        if PROCESS_BOM.get(key[1:]) in lots and isinstance(spec, dict):
            spec["value"] = lots[PROCESS_BOM[key[1:]]]
    params = process.get("ProcessParameters") or {}
    resource = process.get("ResourceParameters") or {}
    if op == "OP50":
        leak = float(v.get("leakRate", 0.4))
        _set(resource, "MeasuredLeakRate", round(leak, 2))
        _set(params, "PressureDecay", round(leak * 13.4, 1))  # decay over the measurement time ~ leak rate
        process["ProcessResult"] = "OK" if leak <= 1.0 else "NOK"
    elif op == "OP60":
        stroke = float(v.get("strokeTime", 0.32))
        _set(resource, "MeasuredStrokeTimeAdvance", round(stroke, 3))
        _set(resource, "MeasuredStrokeTimeRetract", round(stroke * 0.94 + r.gauss(0, 0.002), 3))
        process["ProcessResult"] = "OK" if 0.28 <= stroke <= 0.36 else "NOK"
    if op == "OP10":
        (process.get("ProductParameters") or {}).setdefault("+SerialNumber", {})["value"] = v["serial"]


def apply_inspection(process: dict, v: dict, verdict) -> None:
    resource = process["ResourceParameters"]
    _set(resource, "MeasuredDeltaE76", round(float(v["deltaE"]), 1))
    _set(resource, "MeasuredColourLab", verdict.lab_text if verdict else "")
    process["ProcessResult"] = "OK" if verdict and verdict.colour_ok else "NOK"


def apply_packing(process: dict, v: dict) -> None:
    container = int(v["container"])
    klt = "KLTA01" if container == 1 else "KLTB01"
    process["ProcessParameters"]["+Destination"]["value"] = "${aas:%s}" % klt
    process["ProcessParameters"]["+Slot"]["value"] = int(v["slot"]) + 1
    label = (("KLT A (good part)", "KLT A (Gutteil)") if container == 1
             else ("KLT B (reject)", "KLT B (Ausschuss)"))
    process["ProcessDescription"] = {"en": f"Pick the part and place it in {label[0]}.",
                                     "de": f"Teil greifen und in {label[1]} ablegen."}


def _set(group: dict, name: str, value) -> None:
    if "+" + name in group:
        group["+" + name]["value"] = value


def _jitter(value, r: random.Random, rel: float = 0.012):
    text = str(value)
    decimals = len(text.split(".")[1]) if "." in text else 0
    jittered = float(value) * (1 + r.gauss(0, rel))
    return round(jittered, max(decimals, 1)) if decimals else round(jittered)
