"""Thin client for the BaSyx Go AAS Environment (AAS Part 2 HTTP API, V3): repositories and operation
invocation.

Value-only access ($value) is used for frequent writes; whole submodels are replaced with PUT (create via
POST). Identifiers are base64url-encoded without padding, element paths use dots ("ProcessValues.belt_speed").
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx


class BasyxError(RuntimeError):
    def __init__(self, method: str, path: str, response: httpx.Response):
        super().__init__(f"{method} {path}: HTTP {response.status_code} {response.text[:300]}")
        self.status_code = response.status_code


def b64(identifier: str) -> str:
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


class BasyxClient:
    def __init__(self, base_url: str, timeout: float = 15.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self.http.close()

    # -- shells ------------------------------------------------------------------------------------

    def get_shell(self, aas_id: str) -> dict | None:
        return self._get_or_none(f"/shells/{b64(aas_id)}")

    def list_shells(self, limit: int = 500) -> list[dict]:
        return self._paged("/shells", limit)

    def put_shell(self, shell: dict) -> None:
        self._put_or_post("/shells", shell)

    def delete_shell(self, aas_id: str) -> None:
        self._delete(f"/shells/{b64(aas_id)}")

    def add_submodel_ref(self, aas_id: str, submodel_id: str) -> None:
        ref = {"type": "ModelReference", "keys": [{"type": "Submodel", "value": submodel_id}]}
        response = self.http.post(f"/shells/{b64(aas_id)}/submodel-refs", json=ref)
        if response.status_code not in (200, 201, 409):
            raise BasyxError("POST", "submodel-refs", response)

    # -- submodels ---------------------------------------------------------------------------------

    def get_submodel(self, sm_id: str, blobs: bool = False) -> dict | None:
        """blobs: include Blob values (omitted by default, extent=withoutBlobValue)."""
        return self._get_or_none(f"/submodels/{b64(sm_id)}" + ("?extent=withBlobValue" if blobs else ""))

    def list_submodels(self, semantic_id: str | None = None, limit: int = 500,
                       semantic_key_type: str = "GlobalReference") -> list[dict]:
        # BaSyx Go expects the semantic id as base64url-encoded Reference JSON and matches the reference type
        # too (some IDTA templates, e.g. AID 1.1, use a ModelReference with key type Submodel)
        ref_type = "ExternalReference" if semantic_key_type == "GlobalReference" else "ModelReference"
        reference = {"type": ref_type, "keys": [{"type": semantic_key_type, "value": semantic_id}]}
        params = {"semanticId": b64(json.dumps(reference, separators=(",", ":")))} if semantic_id else {}
        return self._paged("/submodels", limit, params)

    def put_submodel(self, submodel: dict) -> None:
        self._put_or_post("/submodels", submodel)

    def delete_submodel(self, sm_id: str) -> None:
        self._delete(f"/submodels/{b64(sm_id)}")

    def get_value(self, sm_id: str, path: str | None = None) -> Any:
        url = f"/submodels/{b64(sm_id)}" + (f"/submodel-elements/{path}" if path else "") + "/$value"
        response = self.http.get(url)
        if response.status_code >= 300:
            raise BasyxError("GET", url, response)
        return response.json()

    def get_element(self, sm_id: str, path: str) -> dict:
        url = f"/submodels/{b64(sm_id)}/submodel-elements/{path}"
        response = self.http.get(url)
        if response.status_code >= 300:
            raise BasyxError("GET", url, response)
        return response.json()

    def set_value(self, sm_id: str, path: str, value: Any) -> None:
        """Value-only PATCH of a Property: BaSyx Go expects the lexical value as a JSON string."""
        url = f"/submodels/{b64(sm_id)}/submodel-elements/{path}/$value"
        response = self.http.patch(url, json=_lexical(value))
        if response.status_code >= 300:
            raise BasyxError("PATCH", url, response)

    def put_element(self, sm_id: str, path: str, element: dict) -> None:
        url = f"/submodels/{b64(sm_id)}/submodel-elements/{path}"
        response = self.http.put(url, json=element)
        if response.status_code >= 300:
            raise BasyxError("PUT", url, response)

    def put_attachment(self, sm_id: str, path: str, data: bytes, file_name: str, content_type: str) -> None:
        """Uploads the content of a File element (multipart); BaSyx stores it content-addressed (SHA-256
        deduplication) and sets the element value to its managed /aasx/files/... path."""
        url = f"/submodels/{b64(sm_id)}/submodel-elements/{path}/attachment"
        response = self.http.put(url, files={"file": (file_name, data, content_type)},
                                 data={"fileName": file_name})
        if response.status_code >= 300:
            raise BasyxError("PUT", url, response)

    def invoke(self, sm_id: str, path: str, inputs: dict[str, Any], timeout_s: int = 15) -> dict[str, Any]:
        """Synchronous invocation; inputs/outputs as {idShort: value} of Property variables."""
        body = {"inputArguments": [{"value": _property(k, v)} for k, v in inputs.items()],
                "clientTimeoutDuration": f"PT{timeout_s}S"}
        url = f"/submodels/{b64(sm_id)}/submodel-elements/{path}/invoke"
        response = self.http.post(url, json=body, timeout=timeout_s + 5)
        if response.status_code >= 300:
            raise BasyxError("POST", url, response)
        result = response.json()
        outputs = {a["value"]["idShort"]: a["value"].get("value")
                   for a in result.get("outputArguments") or []}
        return {"success": result.get("success", False), "state": result.get("executionState"), **outputs}

    # -- concept descriptions ----------------------------------------------------------------------

    def put_concept_description(self, cd: dict) -> None:
        self._put_or_post("/concept-descriptions", cd)

    def has_concept_description(self, cd_id: str) -> bool:
        return self._get_or_none(f"/concept-descriptions/{b64(cd_id)}") is not None

    # -- helpers -----------------------------------------------------------------------------------

    def _get_or_none(self, url: str) -> dict | None:
        response = self.http.get(url)
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise BasyxError("GET", url, response)
        return response.json()

    def _paged(self, url: str, limit: int, params: dict | None = None) -> list[dict]:
        items, cursor = [], None
        while True:
            query = {"limit": limit, **(params or {}), **({"cursor": cursor} if cursor else {})}
            response = self.http.get(url, params=query)
            if response.status_code >= 300:
                raise BasyxError("GET", url, response)
            body = response.json()
            items += body.get("result", [])
            cursor = (body.get("paging_metadata") or {}).get("cursor")
            if not cursor:
                return items

    def _put_or_post(self, collection: str, obj: dict) -> None:
        response = self.http.put(f"{collection}/{b64(obj['id'])}", json=obj)
        if response.status_code == 404:
            response = self.http.post(collection, json=obj)
        if response.status_code >= 300:
            raise BasyxError("PUT", f"{collection}/{obj['id']}", response)

    def _delete(self, url: str) -> None:
        response = self.http.delete(url)
        if response.status_code not in (200, 204, 404):
            raise BasyxError("DELETE", url, response)


def _lexical(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _property(id_short: str, value: Any) -> dict:
    value_type = ("xs:boolean" if isinstance(value, bool) else "xs:int" if isinstance(value, int)
                  else "xs:double" if isinstance(value, float) else "xs:string")
    return {"modelType": "Property", "idShort": id_short, "valueType": value_type, "value": _lexical(value)}
