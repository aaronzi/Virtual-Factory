"""Entry point: python -m supplier - the supplier portal (port 8190) in front of the supplier AAS environment
(port 8191, ADR-0028). Configuration via environment variables (docs/interfaces/services.md):

    VF_AAS_URL          the supplier environment's repository (batch AAS are written here)
    VF_AAS_PUBLIC_URL   its public URL (links in despatch advices)
    VF_SUPPLIER_PORT    HTTP port (8190)

REST: GET /health · GET /api/articles · POST /api/despatch-advices {"article", "batch"} -> despatch advice
(creates the batch AAS on first request) · GET /api/despatch-advices (issued in this run).
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from vf_common.basyx import BasyxClient, BasyxError
from vf_common.http_api import ApiError, Guard, Request, Response, Router, serve

from .articles import Catalogue
from .batch_aas import BatchPublisher
from .portal import Portal, UnknownLot

log = logging.getLogger("supplier")
ENV = os.environ.get


def router(portal: Portal) -> Router:
    r = Router(Guard.from_env())
    r.add("GET", "/health", lambda q: {"status": "ok", "despatchAdvices": len(portal.advices)}, public=True)
    r.add("GET", "/api/articles", lambda q: [
        {"tag": a.tag, "manufacturerPartId": a.part_id, "customerPartId": a.customer_part_id, "gtin": a.gtin,
         "supplier": a.company.name, "lotPattern": a.profile["lot"]["pattern"]}
        for a in portal.catalogue.articles.values()])
    r.add("GET", "/api/despatch-advices", lambda q: list(portal.advices.values()))
    r.add("POST", "/api/despatch-advices", lambda q: _advice(portal, q), ("svc-erp",))  # the customer's ERP
    return r


def _advice(portal: Portal, q: Request) -> Response:
    body = q.body or {}
    if not body.get("article") or not body.get("batch"):
        raise ApiError(400, "article and batch expected")
    try:
        return Response(200, portal.despatch_advice(str(body["article"]), str(body["batch"])))
    except UnknownLot as exc:
        raise ApiError(404, str(exc)) from exc
    except (BasyxError, httpx.HTTPError) as exc:  # supplier environment not reachable: the ERP retries
        raise ApiError(503, f"supplier AAS environment unavailable: {exc}") from exc


def wait_for(aas: BasyxClient) -> None:
    while True:
        try:
            aas.list_shells(limit=1)
            return
        except Exception as exc:  # noqa: BLE001 - environment starting / importing its preload
            log.info("waiting for the supplier AAS environment: %s", exc)
            time.sleep(3)


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    aas_url = ENV("VF_AAS_URL", "http://localhost:8191")
    aas = BasyxClient(aas_url, timeout=30)
    wait_for(aas)
    portal = Portal(Catalogue(), BatchPublisher(aas), ENV("VF_AAS_PUBLIC_URL", aas_url))
    port = int(ENV("VF_SUPPLIER_PORT", "8190"))
    log.info("supplier portal on :%d, %d articles, environment %s", port, len(portal.catalogue.articles),
             aas_url)
    serve(router(portal), port).serve_forever()


if __name__ == "__main__":
    main()
