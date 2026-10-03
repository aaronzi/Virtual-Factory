"""Line-side staging of component lots (ship-to-line supply, ADR-0028): the first part a feeder of AC01 builds
from a new lot tells the MES that the lot's container is at the line. The MES reports each lot once to the ERP
(`POST {erp}/api/material-staging`), which posts the goods receipt from the supplier's despatch advice; the
supplier publishes the batch AAS with it. Reports run on a background thread (the BPMN task is not delayed);
a failed report is repeated with the next part built from the lot."""

from __future__ import annotations

import logging
import queue
import threading

import httpx

from .lots import COMPONENTS, parse

log = logging.getLogger("mes.staging")


class LotStaging:
    def __init__(self, erp_url: str | None, timeout: float = 30.0):
        self.erp_url = (erp_url or "").rstrip("/")
        self.http = httpx.Client(timeout=timeout) if self.erp_url else None
        self._reported: set[tuple[str, str]] = set()
        self._pending: set[tuple[str, str]] = set()
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._lock = threading.Lock()
        if self.http:
            threading.Thread(target=self._run, daemon=True, name="lot-staging").start()

    def report(self, lots: str | None) -> None:
        """Queues the lots of a released part that were not reported yet ("Node=lot;...")."""
        if not self.http:
            return
        for node, lot in parse(lots).items():
            key = (COMPONENTS[node], lot)
            with self._lock:
                if key in self._reported or key in self._pending:
                    continue
                self._pending.add(key)
            self._queue.put(key)

    def _run(self) -> None:
        while True:
            key = self._queue.get()
            ok = self.send(*key)
            with self._lock:
                self._pending.discard(key)
                if ok:
                    self._reported.add(key)

    def send(self, material: str, lot: str) -> bool:
        try:
            response = self.http.post(f"{self.erp_url}/api/material-staging",
                                      json={"material": material, "lot": lot})
        except httpx.HTTPError as exc:
            log.warning("ERP unreachable, staging of lot %s not reported: %s", lot, exc)
            return False
        if response.status_code >= 500:
            log.warning("staging of lot %s: HTTP %d %s", lot, response.status_code, response.text[:200])
            return False
        log.info("lot %s (%s) reported to the ERP: HTTP %d", lot, material, response.status_code)
        return True
