"""Simulated batch-specific values of purchased components, derived deterministically from the lot number.

The supplier portal (services/supplier) states them in the batch AAS and material certificate of a lot; the
MES writes the same recycled shares into the item-level passport (circularity per component lot). Both must
agree, so both use these functions (ADR-0028).
"""

from __future__ import annotations

import hashlib


def lot_uniform(lot: str, kind: str) -> float:
    """Reproducible number in [0, 1] for a lot and a value kind (e.g. "pre", "post", "energy")."""
    return int(hashlib.sha256(f"{lot}/{kind}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def recycled_share(declared: float, lot: str, kind: str) -> float:
    """Lot-specific recycled share (%) within +-15 % of the declared average (supplier lot certificate)."""
    if not declared:
        return 0.0
    return float(min(100, max(0, round(declared * (0.85 + 0.3 * lot_uniform(lot, kind))))))
