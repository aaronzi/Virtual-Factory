"""Unified Namespace (UNS) registry `godot/config/uns.json`: topics and payloads shared with the Godot
gateway.

Topic kinds (see docs/interfaces/uns.md):
    telemetry  {root}/{device}/{variable}            {"v": value, "ts": ISO 8601}           retained
    event      {root}/{device}/event/{event}         {"event", "device", "session", "seq", "ts", fields...}
    command    {root}/{device}/cmd/{variable}        {"v": value, "corr": id, "source": name}
    ack        {root}/{device}/cmd-resp/{variable}   {"corr", "accepted", "reason", "v", "ts"}
    session    {root}/session, {root}/status         birth message / {"v": "online" | "offline"}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def default_path() -> Path:
    return (Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4]))
            / "godot" / "config" / "uns.json")


@dataclass(frozen=True)
class Uns:
    config: dict

    @classmethod
    def load(cls, path: Path | None = None) -> "Uns":
        return cls(json.loads((path or default_path()).read_text()))

    @property
    def root(self) -> str:
        return self.config["topic_root"]

    def telemetry(self, device: str, variable: str) -> str:
        return self._topic("telemetry", device=device.lower(), variable=variable)

    def event(self, device: str, event: str) -> str:
        return self._topic("events", device=device.lower(), event=event)

    def command(self, device: str, variable: str) -> str:
        return self._topic("commands", device=device.lower(), variable=variable)

    def ack(self, device: str, variable: str) -> str:
        return self.config["commands"]["ack_topic"].format(root=self.root, device=device.lower(),
                                                           variable=variable)

    @property
    def session_topic(self) -> str:
        return self.config["session"]["topic"].format(root=self.root)

    @property
    def status_topic(self) -> str:
        return self.config["session"]["status_topic"].format(root=self.root)

    def all_events(self) -> str:
        return self._topic("events", device="+", event="+")

    def _topic(self, kind: str, **parts: str) -> str:
        return self.config[kind]["topic"].format(root=self.root, **parts)


def broker_address(url: str) -> tuple[str, int]:
    """mqtt://host:port -> (host, port)."""
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 1883


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def telemetry_value(payload: bytes, value_key: str = "v"):
    """Value of a telemetry message; None if the payload is not a JSON object with the value key."""
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    return data.get(value_key) if isinstance(data, dict) else None
