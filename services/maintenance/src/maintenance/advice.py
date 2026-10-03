"""Plain-text advice (en/de) from a prognosis: the recommendation in ConditionMonitoring and the summary shown
in the planning task of a maintenance order."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Component
from .prognosis import Prognosis
from .tasks import MaintenanceTask


def fmt_hours(hours: float | None) -> str:
    if hours is None:
        return "no production"
    if hours < 1.0:
        return f"{hours * 60:.0f} min"
    return f"{hours:.1f} h" if hours < 100 else f"{hours:.0f} h"


def fmt_time(t: float | None) -> str:
    if t is None:
        return "-"
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_value(value: float, unit: str) -> str:
    """Indicator value for people: lengths in mm."""
    return f"{value * 1000:.2f} mm" if unit == "m" else f"{value:.3g} {unit}"


def iso(t: float | None) -> str:
    when = datetime.fromtimestamp(t if t is not None else 0, timezone.utc)
    return when.isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_ms(t: float) -> str:
    """UNS timestamp format (ISO 8601 UTC, milliseconds)."""
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def recommendation(health: str, component: Component, task: MaintenanceTask, p: Prognosis | None,
                   order: str) -> dict[str, str]:
    task_ref = f" ({task.maintenance_id})" if task.maintenance_id else ""
    if p is None:
        return {"en": "No data yet: waiting for the first operating cycles.",
                "de": "Noch keine Daten: warte auf die ersten Arbeitsspiele."}
    if health == "Alarm":
        return {"en": f"Limit reached or failure: {task.name_en}{task_ref} now.",
                "de": f"Grenzwert erreicht oder Ausfall: {task.name_de}{task_ref} sofort."}
    life = (f"{p.rul_cycles_low:.0f} cycles ({fmt_hours(p.rul_hours_low)}, limit before "
            f"{fmt_time(p.failure_time)})")
    life_de = (f"{p.rul_cycles_low:.0f} Arbeitsspiele ({fmt_hours(p.rul_hours_low)}, Grenzwert vor "
               f"{fmt_time(p.failure_time)})")
    if health == "Warning":
        planned = f" - maintenance order {order}" if order else ""
        planned_de = f" - Instandhaltungsauftrag {order}" if order else ""
        return {"en": f"{task.name_en}{task_ref} within at least {life}{planned}.",
                "de": f"{task.name_de}{task_ref} innerhalb von mindestens {life_de}{planned_de}."}
    basis = "trend" if p.method == "TrendFit" else "design data"
    basis_de = "Trend" if p.method == "TrendFit" else "Auslegungsdaten"
    return {"en": f"No action. Remaining useful life at least {life} ({basis}).",
            "de": f"Keine Maßnahme. Restnutzungsdauer mindestens {life_de} ({basis_de})."}


def summary(component: Component, task: MaintenanceTask, p: Prognosis) -> str:
    """Why the order was opened - text of the planning task (Operaton Tasklist, MES terminal)."""
    trend = (f"{component.indicator} {fmt_value(p.value, component.unit)} of "
             f"{fmt_value(component.limit, component.unit)} "
             f"after {p.cycles} cycles, {p.method} over {p.points} measurements "
             f"(confidence {p.confidence:.2f})")
    return (f"{component.name_en}: health index {p.health_index:.2f}; remaining useful life at least "
            f"{p.rul_cycles_low:.0f} cycles ({fmt_hours(p.rul_hours_low)} at {p.throughput:.0f} cycles/h, "
            f"limit before {fmt_time(p.failure_time)}). {trend}. Recommended task: {task.name_en}"
            f"{f' ({task.maintenance_id})' if task.maintenance_id else ''}. "
            f"Plan the maintenance window: next "
            f"order boundary (default) or immediately.")
