"""Runtime reading of AAS references and Asset Interfaces Description (AID 1.1) affordances: which MQTT topic,
QoS/retain flags and JSON keys an interaction uses (docs/interfaces/aas-model.md, ADR-0020).

Shared by the services that configure themselves from the AAS: the ops gateway (Control Component endpoints ->
AID properties/actions) and the MES (AID events). Works on a BaSyx server (`BasyxClient`) or on an environment
dict built by the provisioner (`InMemoryAas`, tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

AID_SEMANTIC_ID = "https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel"
KINDS = {"properties": "property", "actions": "action", "events": "event"}


class AasSource(Protocol):
    def get_submodel(self, sm_id: str) -> dict | None: ...

    def get_shell(self, aas_id: str) -> dict | None: ...

    def list_submodels(self, semantic_id: str | None = None, semantic_key_type: str = "GlobalReference") \
            -> list[dict]: ...


class InMemoryAas:
    """AasSource over an AAS environment dict ({"assetAdministrationShells", "submodels"})."""

    def __init__(self, env: dict):
        self.env = env

    def get_submodel(self, sm_id: str) -> dict | None:
        return next((s for s in self.env["submodels"] if s["id"] == sm_id), None)

    def get_shell(self, aas_id: str) -> dict | None:
        return next((s for s in self.env["assetAdministrationShells"] if s["id"] == aas_id), None)

    def list_submodels(self, semantic_id: str | None = None, semantic_key_type: str = "GlobalReference") \
            -> list[dict]:
        return [s for s in self.env["submodels"] if semantic_id is None or semantic_of(s) == semantic_id]


@dataclass(frozen=True)
class Form:
    """One WoT form of an affordance (MQTT binding): topic = href without the leading '/'."""
    topic: str
    op: str = ""
    content_type: str = "application/json"
    qos: int = 0
    retain: bool = False
    control_packet: str = ""


@dataclass(frozen=True)
class Affordance:
    name: str
    kind: str                                  # property | action | event
    form: Form
    keys: dict[str, str] = field(default_factory=dict)      # payload schema: idShort -> JSON key
    ack: Form | None = None                    # action: acknowledgement form (op queryaction)
    ack_keys: dict[str, str] = field(default_factory=dict)  # action: output (ack) schema

    def key(self, name: str, default: str) -> str:
        return self.keys.get(name, default)

    def ack_key(self, name: str, default: str) -> str:
        return self.ack_keys.get(name, default)


class Resolver:
    """Follows ModelReferences into submodels; caches every submodel read (`sources` = ids read)."""

    def __init__(self, source: AasSource):
        self.source = source
        self.cache: dict[str, dict] = {}

    @property
    def sources(self) -> set[str]:
        return set(self.cache)

    def submodel(self, sm_id: str) -> dict:
        if sm_id not in self.cache:
            submodel = self.source.get_submodel(sm_id)
            if submodel is None:
                raise LookupError(f"submodel {sm_id} not found")
            self.cache[sm_id] = submodel
        return self.cache[sm_id]

    def element(self, ref: dict) -> dict:
        keys = ref["keys"]
        if keys[0]["type"] != "Submodel":
            raise LookupError(f"reference does not start at a submodel: {keys[0]}")
        element = {"value": self.submodel(keys[0]["value"])["submodelElements"]}
        for key in keys[1:]:
            element = child(element.get("value") or [], key["value"])
        return element

    def affordance(self, ref: dict) -> Affordance:
        """AID affordance a reference points to (…InteractionMetadata.<properties|actions|events>.<name>)."""
        keys = ref["keys"]
        kind = KINDS.get(keys[-2]["value"]) if len(keys) > 2 else None
        if kind is None:
            raise LookupError(f"not an AID affordance reference: {'/'.join(k['value'] for k in keys)}")
        return affordance(self.element(ref), kind)


def affordance(element: dict, kind: str) -> Affordance:
    elements = element.get("value") or []
    schema = {"property": "properties", "action": "input", "event": "data"}[kind]
    output = child(elements, "output", required=False)
    ack = child(elements, "ackForms", required=False)
    return Affordance(element["idShort"], kind, form(child(elements, "forms")), schema_keys(elements, schema),
                      form(ack) if ack else None, schema_keys([output] if output else [], "output"))


def form(element: dict) -> Form:
    values = {e["idShort"]: e.get("value") for e in element.get("value") or []
              if e.get("modelType") == "Property"}
    return Form(topic=str(values.get("href") or "").lstrip("/"), op=values.get("op") or "",
                content_type=values.get("contentType") or "application/json",
                qos=int(values.get("mqv_qos") or 0), retain=str(values.get("mqv_retain")).lower() == "true",
                control_packet=values.get("mqv_controlPacket") or "")


def schema_keys(elements: list[dict], name: str) -> dict[str, str]:
    """{idShort: JSON key} of the object properties of a data schema element (`properties` directly, or
    `<name>.properties` for input/output/data schemas)."""
    container = child(elements, name, required=False)
    if container is None:
        return {}
    if name != "properties":
        container = child(container.get("value") or [], "properties", required=False) or {}
    out = {}
    for entry in container.get("value") or []:
        key = child(entry.get("value") or [], "key", required=False)
        out[entry["idShort"]] = (key or {}).get("value") or entry["idShort"]
    return out


def aid_submodels(source: AasSource) -> list[dict]:
    """All AID submodels. The IDTA AID 1.1 template's semanticId is a ModelReference (key type Submodel); both
    reference forms are accepted."""
    found = {s["id"]: s for s in source.list_submodels(semantic_id=AID_SEMANTIC_ID)}
    models = source.list_submodels(semantic_id=AID_SEMANTIC_ID, semantic_key_type="Submodel")
    found |= {s["id"]: s for s in models}
    return list(found.values())


def events(aid: dict) -> list[Affordance]:
    """All event affordances of all interfaces of an AID submodel."""
    out = []
    for interface in aid.get("submodelElements") or []:
        meta = child(interface.get("value") or [], "InteractionMetadata", required=False) or {}
        collection = child(meta.get("value") or [], "events", required=False) or {}
        out += [affordance(e, "event") for e in collection.get("value") or []]
    return out


def semantic_of(element: dict) -> str | None:
    keys = (element.get("semanticId") or {}).get("keys") or [{}]
    return keys[0].get("value")


def value_of(elements: list[dict], id_short: str, default=None):
    found = child(elements, id_short, required=False)
    return found.get("value", default) if found else default


def child(elements: list[dict], id_short: str, required: bool = True) -> dict | None:
    if id_short.isdigit():  # SubmodelElementList index
        return elements[int(id_short)]
    found = next((e for e in elements if e.get("idShort") == id_short), None)
    if found is None and required:
        raise LookupError(f"element '{id_short}' not found")
    return found
