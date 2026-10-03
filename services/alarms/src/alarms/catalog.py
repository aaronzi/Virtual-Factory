"""Master alarm database (ISA-18.2 rationalization) from `infra/alarms.json`: code, texts, priority, class,
PLC reaction, response time, consequence, remedy and the designed suppression rules."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def default_path() -> Path:
    return Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4])) / "infra" / "alarms.json"


@dataclass(frozen=True)
class AlarmDefinition:
    code: int
    source: str
    text_en: str
    text_de: str
    priority: str
    rank: int                       # 1 = most urgent
    alarm_class: str = ""
    reaction: str = ""
    response_s: int = 0
    consequence_en: str = ""
    remedy_en: str = ""
    remedy_de: str = ""
    suppressed_by: tuple[int, ...] = ()
    suppress_in_states: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        return {"code": self.code, "source": self.source, "text": {"en": self.text_en, "de": self.text_de},
                "priority": self.priority, "priorityRank": self.rank, "class": self.alarm_class,
                "reaction": self.reaction, "responseTimeS": self.response_s,
                "consequence": self.consequence_en,
                "remedy": {"en": self.remedy_en, "de": self.remedy_de},
                "suppressedBy": list(self.suppressed_by), "suppressInStates": list(self.suppress_in_states)}


@dataclass(frozen=True)
class Catalog:
    alarms: dict[int, AlarmDefinition]
    max_shelve_s: int = 28800
    stale_after_s: int = 3600
    chattering: dict = field(default_factory=lambda: {"count": 3, "window_s": 60})
    flood_per_10min: int = 10

    @classmethod
    def load(cls, path: Path | None = None) -> "Catalog":
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
        ranks = data["priorities"]
        alarms = {a["code"]: AlarmDefinition(
            code=a["code"], source=a.get("source", data["source"]), text_en=a["text_en"],
            text_de=a["text_de"],
            priority=a["priority"], rank=ranks[a["priority"]], alarm_class=a.get("class", ""),
            reaction=a.get("reaction", ""), response_s=a.get("response_s", 0),
            consequence_en=a.get("consequence_en", ""), remedy_en=a.get("remedy_en", ""),
            remedy_de=a.get("remedy_de", ""), suppressed_by=tuple(a.get("suppressed_by", [])),
            suppress_in_states=tuple(a.get("suppress_in_states", []))) for a in data["alarms"]}
        return cls(alarms, data.get("max_shelve_s", 28800), data.get("stale_after_s", 3600),
                   data.get("chattering", {"count": 3, "window_s": 60}),
                   data.get("flood", {}).get("per_10min", 10))

    def get(self, code: int) -> AlarmDefinition:
        """Definition of a code; codes missing from the database get a generic Medium definition (they are
        still journaled - an unrationalized alarm is itself a finding)."""
        return self.alarms.get(code) or AlarmDefinition(code, "PLC01", f"Alarm {code} (not rationalized)",
                                                        f"Alarm {code} (nicht rationalisiert)", "Medium", 3)
