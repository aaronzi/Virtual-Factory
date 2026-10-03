"""`RegistryAas`: the read/write surface of `BasyxClient` used by the services, but every shell and submodel
is located through the registries (`AasResolver`) and fetched from the repository its descriptor points to -
also in a federated second environment. Implements `vf_common.aid.AasSource`.

Creating new shells/submodels is not routed: a service writes new AAS into its own repository (`BasyxClient`
on VF_AAS_URL); the registry integration of the repository registers them.
"""

from __future__ import annotations

from typing import Any

from .basyx import BasyxClient, BasyxError
from .resolver import AasResolver, NotResolved, ShellEndpoint, SubmodelEndpoint


class RegistryAas:
    def __init__(self, resolver: AasResolver):
        self.resolver = resolver

    # -- AasSource ---------------------------------------------------------------------------------

    def get_shell(self, aas_id: str) -> dict | None:
        try:
            endpoint = self.resolver.shell(aas_id)
        except NotResolved:
            return None
        return self._repo(endpoint).get_shell(aas_id)

    def get_submodel(self, sm_id: str, blobs: bool = False) -> dict | None:
        try:
            endpoint = self.resolver.submodel(sm_id)
        except NotResolved:
            return None
        return self._repo(endpoint).get_submodel(sm_id, blobs=blobs)

    def list_submodels(self, semantic_id: str | None = None, limit: int = 500,
                       semantic_key_type: str = "GlobalReference") -> list[dict]:
        """Submodels with this semanticId found in the submodel registries (content from their repositories).
        Without a semanticId: a reachability probe of the first registry (empty list)."""
        if semantic_id is None:
            self.resolver.infra[0].submodel_descriptors(limit=1)
            return []
        out = []
        for endpoint in self.resolver.find_submodels(semantic_id):
            submodel = self._repo(endpoint).get_submodel(endpoint.id)
            if submodel:
                out.append(submodel)
        return out

    # -- element access (routed) -------------------------------------------------------------------

    def get_value(self, sm_id: str, path: str | None = None) -> Any:
        return self._sm_repo(sm_id).get_value(sm_id, path)

    def get_element(self, sm_id: str, path: str) -> dict:
        return self._sm_repo(sm_id).get_element(sm_id, path)

    def set_value(self, sm_id: str, path: str, value: Any) -> None:
        try:
            self._sm_repo(sm_id).set_value(sm_id, path, value)
        except BasyxError as exc:
            if exc.status_code == 404:  # moved or re-created: resolve again next time
                self.resolver.invalidate(sm_id=sm_id)
            raise

    def put_element(self, sm_id: str, path: str, element: dict) -> None:
        self._sm_repo(sm_id).put_element(sm_id, path, element)

    def invoke(self, sm_id: str, path: str, inputs: dict[str, Any], timeout_s: int = 15) -> dict[str, Any]:
        return self._sm_repo(sm_id).invoke(sm_id, path, inputs, timeout_s)

    def _sm_repo(self, sm_id: str) -> BasyxClient:
        return self._repo(self.resolver.submodel(sm_id))

    def _repo(self, endpoint: ShellEndpoint | SubmodelEndpoint) -> BasyxClient:
        return self.resolver.repository(endpoint)
