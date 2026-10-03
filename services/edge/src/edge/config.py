"""What the edge connector bridges, read from the AAS (ADR-0024): every Asset Interfaces Description with an
OPC UA interface (southbound, the controller's server) and an MQTT interface (northbound, the UNS).
Affordances are paired by name - the AID describes the same data point twice:

    property  OPC UA monitored item (href)    -> UNS telemetry topic, payload keys of the MQTT property
    event     OPC UA event type (href)        -> UNS event topic (flat JSON: event, device, session, ...)
    action    UNS command topic (MQTT action) -> OPC UA method call -> UNS ack topic (ackForms)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vf_common.aid import AasSource, Affordance, affordances, aid_submodels


@dataclass(frozen=True)
class Route:
    """One paired affordance: `ua` (OPC UA side) and `uns` (MQTT side)."""
    name: str
    ua: Affordance
    uns: Affordance


@dataclass
class AssetLink:
    aid_id: str
    endpoint: str                                   # EndpointMetadata.base of the OPC UA interface
    properties: list[Route] = field(default_factory=list)
    events: list[Route] = field(default_factory=list)
    actions: list[Route] = field(default_factory=list)

    def describe(self) -> str:
        return (f"{self.endpoint}: {len(self.properties)} properties, {len(self.events)} events, "
                f"{len(self.actions)} actions ({self.aid_id})")


def resolve(source: AasSource) -> list[AssetLink]:
    links = []
    for aid in aid_submodels(source):
        link = _link(aid)
        if link is not None:
            links.append(link)
    return links


def _link(aid: dict) -> AssetLink | None:
    routes: dict[str, list[Route]] = {}
    base = ""
    for collection in ("properties", "events", "actions"):
        found = affordances(aid, collection)
        uns = {a.name: a for a in found if a.protocol == "mqtt"}
        ua = [a for a in found if a.protocol == "opcua"]
        routes[collection] = [Route(a.name, a, uns[a.name]) for a in ua if a.name in uns]
        base = base or next((a.base for a in ua), "")
    if not base:
        return None
    return AssetLink(aid["id"], base, routes["properties"], routes["events"], routes["actions"])
