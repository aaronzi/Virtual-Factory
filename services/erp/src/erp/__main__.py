"""Entry point: python -m erp (configuration via environment variables, see docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os
import threading
import time

from vf_common.bpmn import BpmnClient
from vf_common.http_api import serve

from .api import router
from .master_data import load_materials
from .receipts import GoodsReceipts, SupplierPortal
from .release import OrderRelease, Settings
from .store import ErpStore

log = logging.getLogger("erp")
ENV = os.environ.get


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    store = ErpStore(load_materials())
    settings = Settings(auto_release=ENV("VF_ERP_AUTO_RELEASE", "true").lower() in ("1", "true", "yes"),
                        standing_quantity=int(ENV("VF_ERP_STANDING_QTY", "48")))
    bpmn = BpmnClient(ENV("VF_BPMN_URL", "http://localhost:8092/engine-rest"))
    release = OrderRelease(store, bpmn, settings)
    port = int(ENV("VF_ERP_PORT", "8098"))
    portal = SupplierPortal(ENV("VF_SUPPLIER_URL", "")) if ENV("VF_SUPPLIER_URL") else None
    api = router(store, release, settings, GoodsReceipts(store, portal))
    threading.Thread(target=serve(api, port).serve_forever, daemon=True, name="http").start()
    log.info("ERP simulator on :%d (auto release %s, standing order %d parts)", port, settings.auto_release,
             settings.standing_quantity)
    interval = float(ENV("VF_ERP_PLANNING_S", "5"))
    while True:
        try:
            release.tick()
        except Exception as exc:  # noqa: BLE001 - engine not reachable / process not deployed yet: retry
            log.info("planning step: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
