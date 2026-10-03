"""Supplier-specific footprints per batch (ADR-0028): the CarbonFootprint submodel of the supplier's batch
AAS, published in the supplier AAS environment when the batch was despatched.

    BoM line (component type, globalAssetId) -> registry descriptor of the component type AAS -> specific
    asset id `gtin` (purchased parts only) -> GS1 Digital Link of the batch <domain>/01/<GTIN>/10/<lot>
    -> federated discovery (VF_AAS_REGISTRIES) -> batch AAS -> submodel with the CarbonFootprint semanticId
    -> first entry: PcfCO2eq per piece, PrimaryDataShare

Footprints of a batch do not change after publication and are cached for the life of the service. A batch the
discovery does not know (yet) is asked again after `miss_ttl_s`; an unreachable environment is not cached. In
both cases the chain falls back to the declared type average (secondary data)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

from vf_common.basyx import BasyxError
from vf_common.digital_link import batch_link
from vf_common.resolver import AasResolver, NotResolved

from .suppliers import CARBON_FOOTPRINT, BomLine, ComponentFootprint, first_entry

log = logging.getLogger("sustainability.supplier_batches")


class SupplierBatchFootprints:
    def __init__(self, resolver: AasResolver, miss_ttl_s: float = 30.0,
                 clock: Callable[[], float] = time.monotonic):
        self.resolver, self.miss_ttl_s, self.clock = resolver, miss_ttl_s, clock
        self._gtins: dict[str, str | None] = {}      # component type asset id -> GTIN (None: in-house)
        self._found: dict[str, ComponentFootprint] = {}  # batch Digital Link -> footprint
        self._missed: dict[str, float] = {}          # batch Digital Link -> time to ask again
        self._lock = threading.Lock()

    def footprint(self, line: BomLine, batch: str | None) -> ComponentFootprint | None:
        if not batch or not line.global_asset_id:
            return None
        try:
            gtin = self._gtin(line.global_asset_id)
            if not gtin:
                return None  # in-house component: no supplier batches
            link = batch_link(gtin, batch)
            with self._lock:
                if link in self._found or self._missed.get(link, 0.0) > self.clock():
                    return self._found.get(link)
            found = self._read(link, batch)
        except NotResolved as exc:
            log.info("no supplier batch AAS for %s %s (%s): declared type average", line.node, batch, exc)
            with self._lock:
                self._missed[batch_link(gtin, batch)] = self.clock() + self.miss_ttl_s
            return None
        except (httpx.HTTPError, BasyxError) as exc:
            log.warning("supplier environment unavailable for %s %s: %s", line.node, batch, exc)
            return None
        with self._lock:
            self._found[link] = found
        return found

    def _gtin(self, type_asset_id: str) -> str | None:
        """GTIN of a purchased component type (specific asset id of its AAS in the registry)."""
        if type_asset_id not in self._gtins:
            try:
                descriptor = self.resolver.resolve_asset(type_asset_id).descriptor
            except NotResolved:
                descriptor = {}  # component type without registered AAS: nothing to look up
            ids = {s.get("name"): s.get("value") for s in descriptor.get("specificAssetIds") or []}
            self._gtins[type_asset_id] = ids.get("gtin")
        return self._gtins[type_asset_id]

    def _read(self, link: str, batch: str) -> ComponentFootprint:
        shell = self.resolver.resolve_asset(link)
        endpoint = self.resolver.submodel_of(shell.aas_id, semantic_id=CARBON_FOOTPRINT)
        submodel = self.resolver.repository(endpoint).get_submodel(endpoint.id)
        entry = first_entry(submodel or {"submodelElements": []})
        if entry.get("PcfCO2eq") is None:
            raise NotResolved(f"batch AAS {shell.aas_id} has no PCF")
        log.info("batch %s: supplier PCF %s kg (%s, environment %s)", batch, entry["PcfCO2eq"], link,
                 shell.environment)
        return ComponentFootprint(float(entry["PcfCO2eq"]), "supplier-batch", endpoint.id, batch, "primary",
                                  float(entry.get("PrimaryDataShare") or 100.0), link)
