"""Entry point: python -m plc_comm - the communication module of a controller (ADR-0024): OPC UA server on
opc.tcp://<host>:4840 plus the backplane port 4841 for the simulated CPU (Godot).

Environment: VF_PLC_INSTANCE (PLC01), VF_OPCUA_BIND (endpoint of the registry with host 0.0.0.0),
VF_BACKPLANE_BIND (0.0.0.0:<port of the registry's backplane URL>), LOG_LEVEL.
The address space is engineered from the FMI model description of the instance (asset data) and the UNS
registry (opcua.servers.<instance>)."""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

from .backplane import Backplane
from .module import bind_endpoint, comm_module, engineer, load_uns

log = logging.getLogger("plc-comm")


async def run(instance: str) -> None:
    uns = load_uns()
    space = engineer(instance, uns)
    default_port = urlparse(uns["opcua"]["servers"][instance]["backplane"]).port or 4841
    host, _, port = (os.environ.get("VF_BACKPLANE_BIND") or f"0.0.0.0:{default_port}").rpartition(":")
    bind = os.environ.get("VF_OPCUA_BIND") or bind_endpoint(space.endpoint)
    async with comm_module(space, bind, host, int(port)) as module:
        log.info("OPC UA server %s (namespace %s, %d nodes, %d event types), listening on %s", space.endpoint,
                 space.namespace, len(space.nodes), len(space.events), bind)
        await _report(module.backplane)


async def _report(backplane: Backplane, every_s: float = 60.0) -> None:
    last = dict(backplane.stats)
    while True:
        await asyncio.sleep(every_s)
        stats = dict(backplane.stats)
        writes = stats["writes"] - last["writes"]
        latency = (stats["write_ms"] - last["write_ms"]) / writes if writes else 0.0
        log.info("CPU %s: %.1f images/s, %d events, %d writes (mean %.1f ms) in the last %.0f s",
                 "connected" if backplane.connected else "not connected",
                 (stats["images"] - last["images"]) / every_s, stats["events"] - last["events"], writes,
                 latency, every_s)
        last = stats


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("asyncua").setLevel(logging.ERROR)
    asyncio.run(run(os.environ.get("VF_PLC_INSTANCE", "PLC01")))


if __name__ == "__main__":
    main()
