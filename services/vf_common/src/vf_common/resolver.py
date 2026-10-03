"""Resolution chain of a real AAS deployment (ADR-0023):

    asset id (globalAssetId, e.g. a GS1 Digital Link, or specificAssetIds such as serialNumber)
      -> Discovery  /lookup/shells          -> AAS id
      -> AAS Registry /shell-descriptors    -> shell endpoint (href) + submodel ids/endpoints
      -> Submodel Registry                  -> submodel idShort / semanticId / endpoint
      -> repository (href)                  -> shell / submodel content

Several environments may be configured (federation, `RegistryConfig`); the first one that knows an id wins.
An environment that is unreachable is skipped (logged) as long as another one answers; only if the id is found
nowhere and an environment failed, its error is raised (callers retry instead of concluding "unknown").
Positive results are cached for `cache_ttl_s`; BaSyx change events (`on_event`) drop affected entries early.
AAS and submodel ids are never constructed by convention here.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from .aid import semantic_of
from .basyx import BasyxClient, BasyxError
from .registry import InfrastructureClient, RegistryConfig, endpoint_href, repository_base

log = logging.getLogger("vf.resolver")


class NotResolved(LookupError):
    """No configured discovery / registry knows the asset, AAS or submodel."""


@dataclass(frozen=True)
class SubmodelEndpoint:
    id: str
    href: str            # public endpoint as written in the descriptor
    environment: str
    id_short: str | None = None
    semantic_id: str | None = None


@dataclass(frozen=True)
class ShellEndpoint:
    aas_id: str
    href: str
    environment: str
    descriptor: dict = field(repr=False, compare=False)

    @property
    def global_asset_id(self) -> str | None:
        return self.descriptor.get("globalAssetId")

    @property
    def submodel_ids(self) -> list[str]:
        return [d["id"] for d in self.descriptor.get("submodelDescriptors") or []]


class AasResolver:
    def __init__(self, config: RegistryConfig, auth: httpx.Auth | None = None,
                 client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic):
        self.config, self.auth, self.clock = config, auth, clock
        self.http = client or httpx.Client(timeout=config.timeout_s, auth=auth)
        self.infra = [InfrastructureClient(e, self.http) for e in config.environments]
        self._cache: dict[tuple[str, str], tuple[float, object]] = {}
        self._repos: dict[str, BasyxClient] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, auth: httpx.Auth | None = None) -> AasResolver:
        return cls(RegistryConfig.from_env(), auth=auth)

    # -- discovery ---------------------------------------------------------------------------------

    def lookup(self, global_asset_id: str | None = None, **specific: str) -> list[str]:
        """AAS ids for an asset over all discovery services (globalAssetId and/or specific asset ids)."""
        query = {**({"globalAssetId": global_asset_id} if global_asset_id else {}), **specific}
        if not query:
            raise ValueError("lookup needs at least one asset id")
        key = ("lookup", json.dumps(query, sort_keys=True))
        cached = self._get(key)
        if cached is not None:
            return cached
        found: list[str] = []
        try:
            for _, ids in self._ask(lambda infra: infra.lookup_shells(query)):
                found += [i for i in ids if i not in found]
        except (httpx.HTTPError, BasyxError):
            if not found:
                raise  # no environment knows it and one could not be asked
        return self._put(key, found) if found else found

    def resolve_asset(self, global_asset_id: str | None = None, **specific: str) -> ShellEndpoint:
        """Shell endpoint of the (first) AAS describing the asset."""
        for aas_id in self.lookup(global_asset_id, **specific):
            try:
                return self.shell(aas_id)
            except NotResolved:
                continue  # stale discovery entry
        raise NotResolved(f"no AAS for asset {global_asset_id or ''} {specific or ''}".strip())

    # -- registries --------------------------------------------------------------------------------

    def shell(self, aas_id: str) -> ShellEndpoint:
        cached = self._get(("shell", aas_id))
        if cached is not None:
            return cached
        for infra, descriptor in self._ask(lambda infra: infra.shell_descriptor(aas_id)):
            href = endpoint_href(descriptor, "AAS-") if descriptor else None
            if href:
                return self._put(("shell", aas_id), ShellEndpoint(aas_id, href, infra.environment.name,
                                                                   descriptor))
        raise NotResolved(f"AAS {aas_id} is not registered")

    def submodel(self, sm_id: str) -> SubmodelEndpoint:
        cached = self._get(("submodel", sm_id))
        if cached is not None:
            return cached
        for infra, descriptor in self._ask(lambda infra: infra.submodel_descriptor(sm_id)):
            if descriptor and endpoint_href(descriptor, "SUBMODEL-"):
                return self._put(("submodel", sm_id), _submodel(descriptor, infra.environment.name))
        raise NotResolved(f"submodel {sm_id} is not registered")

    def submodels(self, aas_id: str) -> list[SubmodelEndpoint]:
        out = []
        for sm_id in self.shell(aas_id).submodel_ids:
            try:
                out.append(self.submodel(sm_id))
            except NotResolved:
                continue  # referenced but not (yet) registered
        return out

    def submodel_of(self, aas_id: str, id_short: str | None = None,
                    semantic_id: str | None = None) -> SubmodelEndpoint:
        """The AAS's submodel with this idShort and/or semanticId."""
        for sm in self.submodels(aas_id):
            if (id_short is None or sm.id_short == id_short) and \
                    (semantic_id is None or sm.semantic_id == semantic_id):
                return sm
        raise NotResolved(f"AAS {aas_id} has no submodel {id_short or semantic_id}")

    def submodel_of_asset(self, global_asset_id: str, id_short: str) -> SubmodelEndpoint:
        """Asset id -> discovery -> registry -> the submodel with this idShort."""
        return self.submodel_of(self.resolve_asset(global_asset_id).aas_id, id_short)

    def find_submodels(self, semantic_id: str) -> list[SubmodelEndpoint]:
        """All registered submodels with this semanticId, over all submodel registries."""
        out: dict[str, SubmodelEndpoint] = {}
        try:
            for infra, descriptors in self._ask(lambda infra: infra.submodel_descriptors()):
                for descriptor in descriptors:
                    if semantic_of(descriptor) == semantic_id and descriptor["id"] not in out \
                            and endpoint_href(descriptor, "SUBMODEL-"):
                        out[descriptor["id"]] = self._put(("submodel", descriptor["id"]),
                                                          _submodel(descriptor, infra.environment.name))
        except (httpx.HTTPError, BasyxError):
            if not out:
                raise
        return list(out.values())

    def _ask(self, call: Callable[[InfrastructureClient], object]):
        """(environment client, answer) per environment in order (generator: a caller that found what it
        needs stops asking). Unreachable environments are skipped; when all answers were consumed and one
        environment failed, its error is raised at the end."""
        failure: Exception | None = None
        for infra in self.infra:
            try:
                answer = call(infra)
            except (httpx.HTTPError, BasyxError) as exc:
                log.warning("AAS environment %s unavailable: %s", infra.environment.name, exc)
                failure = failure or exc
                continue
            yield infra, answer
        if failure is not None:
            raise failure

    # -- repositories ------------------------------------------------------------------------------

    def repository(self, endpoint: ShellEndpoint | SubmodelEndpoint) -> BasyxClient:
        """Client of the repository that serves the endpoint (one client per repository base URL)."""
        base = self.config.reachable(repository_base(endpoint.href))
        with self._lock:
            if base not in self._repos:
                http = httpx.Client(base_url=base, timeout=self.config.timeout_s, auth=self.auth)
                self._repos[base] = BasyxClient(base, client=http)
            return self._repos[base]

    def reachable(self, href: str) -> str:
        return self.config.reachable(href)

    # -- cache -------------------------------------------------------------------------------------

    def invalidate(self, aas_id: str | None = None, sm_id: str | None = None) -> None:
        with self._lock:
            for key in [k for k in self._cache
                        if (aas_id and k == ("shell", aas_id)) or (sm_id and k == ("submodel", sm_id))
                        or (aas_id and k[0] == "lookup")]:
                del self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def on_event(self, topic: str, payload: bytes) -> None:
        """BaSyx CloudEvent (MQTT eventing, `.../shell|submodel/<action>`): drops cached descriptors of
        changed shells and of created / deleted submodels. Submodel value updates keep their endpoints."""
        entity, _, action = topic.rpartition("/")
        entity = entity.rpartition("/")[2]
        if entity not in ("shell", "submodel") or (entity == "submodel" and action == "updated"):
            return
        try:
            event = json.loads(payload)
            subject = event.get("subject") or (event.get("data") or {}).get("submodelId")
        except (ValueError, AttributeError):
            return
        if subject and entity == "shell":
            self.invalidate(aas_id=subject)
        elif subject:
            self.invalidate(sm_id=subject)

    def _get(self, key: tuple[str, str]):
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > self.clock():
                return hit[1]
            return None

    def _put(self, key: tuple[str, str], value):
        with self._lock:
            self._cache[key] = (self.clock() + self.config.cache_ttl_s, value)
        return value


def _submodel(descriptor: dict, environment: str) -> SubmodelEndpoint:
    return SubmodelEndpoint(descriptor["id"], endpoint_href(descriptor, "SUBMODEL-") or "", environment,
                            descriptor.get("idShort"), semantic_of(descriptor))


def until_resolved(resolve: Callable[[], object], what: str, retry_s: float = 5.0):
    """Calls `resolve` until it succeeds (start-up: the AAS server may still be importing its preload)."""
    while True:
        try:
            return resolve()
        except (NotResolved, httpx.HTTPError, RuntimeError) as exc:
            log.info("waiting for %s in discovery/registry: %s", what, exc)
            time.sleep(retry_s)
