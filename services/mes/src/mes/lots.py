"""Component lots of a workpiece (traceability, ADR-0021).

The assembly cell AC01 reports the lots it built into each part with `part_released` (field `lots`, FMI
output `last_lots`: "Barrel=L2609-0419;EndCapFront=DGP-260914-F;..."; keys are the BoM nodes of PC3280_TYPE).
The lots originate on the shop floor: every feeder of the cell changes its lot after its own number of parts
(godot/devices/assembly_cell/model/component_lots.gd). Older simulation builds without `last_lots` get lots
derived from the blueprint lots in blocks of FALLBACK_BLOCK parts (documented fallback, not traceability).

Recycled content per lot: the type declares the average shares per component; the lot-specific shares are
those of the supplier's material certificate of the lot (batch AAS of the supplier environment, ADR-0028) and
are derived deterministically from the lot number (vf_common.lot_values, within +-15 % of the declared share).
"""

from __future__ import annotations

import re

from vf_common.lot_values import recycled_share  # noqa: F401 - re-exported for passport.py

# BoM node of PC3280_TYPE -> article number (ComponentId in material composition and circularity)
COMPONENTS = {"Barrel": "5032-1001", "EndCapFront": "5032-1002", "EndCapRear": "5032-1003",
              "PistonRod": "5032-1004", "Piston": "5032-1005", "SealKit": "5032-1006",
              "ScrewM5x16": "9001-0516", "CushioningScrew": "5032-1008", "ProtectiveCap": "5032-1009"}
NODE_OF_ARTICLE = {article: node for node, article in COMPONENTS.items()}
# ProcessBoM element of the executed processes -> BoM node
PROCESS_BOM = {"PistonRodLot": "PistonRod", "PistonLot": "Piston", "SealKitLot": "SealKit",
               "BarrelLot": "Barrel", "EndCapFrontLot": "EndCapFront", "EndCapRearLot": "EndCapRear",
               "ScrewLot": "ScrewM5x16", "CushioningScrewLot": "CushioningScrew",
               "ProtectiveCapLot": "ProtectiveCap"}
FALLBACK_BLOCK = 250
LOT_NUMBER = re.compile(r"(\d+)(\D*)$")


def parse(text: str | None) -> dict[str, str]:
    """'Node=lot;Node=lot' -> {node: lot} (unknown nodes and empty pairs are ignored)."""
    lots = {}
    for pair in (text or "").split(";"):
        node, _, lot = pair.partition("=")
        if node.strip() in COMPONENTS and lot.strip():
            lots[node.strip()] = lot.strip()
    return lots


def lots_for(v: dict, base: dict[str, str]) -> dict[str, str]:
    """Lots of the part: as reported by the cell, missing nodes from the fallback."""
    reported = parse(v.get("lots"))
    if len(reported) == len(COMPONENTS):
        return reported
    return {**fallback(v["serial"], base), **reported}


def fallback(serial: str, base: dict[str, str]) -> dict[str, str]:
    block = int(serial.rsplit("-", 1)[-1]) // FALLBACK_BLOCK
    return {node: shift(lot, block) for node, lot in base.items()}


def shift(lot: str, block: int) -> str:
    """Advances the trailing number of a lot by `block` (L2609-0412 -> L2609-0414 for block 2)."""
    match = LOT_NUMBER.search(lot)
    if not match:
        return lot
    digits = match.group(1)
    return lot[:match.start(1)] + str(int(digits) + block).zfill(len(digits)) + match.group(2)
