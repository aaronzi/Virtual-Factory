"""The communication module as a unit: address space engineered from the asset data, asyncua server and
backplane server (used by __main__ and by the tests of plc_comm, edge and ops gateway)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse

from asyncua import Server

from provisioner.build import REPO, load_assets
from provisioner.interfaces_opcua import device_models, field_types
from vf_common.opcua_plc import AddressSpace, address_space
from vf_common.opcua_security import OpcUaSecurity, secure_server

from .address_space import PlcAddressSpace
from .backplane import Backplane


def load_uns(repo: Path = REPO) -> dict:
    return json.loads((repo / "godot" / "config" / "uns.json").read_text())


def engineer(instance: str, uns: dict, repo: Path = REPO) -> AddressSpace:
    """Address space from the asset data: model description of the instance, field types of the event fields
    of other devices."""
    models = device_models(repo, load_assets(repo / "aas" / "data"))
    return address_space(instance, list(models[instance].variables), uns, field_types(models))


def bind_endpoint(endpoint: str, host: str = "0.0.0.0") -> str:
    """The registry endpoint with another host (the server listens on all interfaces)."""
    parsed = urlparse(endpoint)
    return endpoint.replace(parsed.netloc, f"{host}:{parsed.port or 4840}", 1)


@dataclass
class CommModule:
    server: Server
    plc: PlcAddressSpace
    backplane: Backplane


@asynccontextmanager
async def comm_module(space: AddressSpace, opcua_bind: str, backplane_host: str, backplane_port: int,
                      security: OpcUaSecurity | None = None) -> AsyncIterator[CommModule]:
    server = Server()
    await server.init()
    server.set_endpoint(opcua_bind)
    server.set_server_name(f"{space.instance} communication module (Virtual Factory, simulated)")
    await server.set_application_uri(f"{space.namespace}:server")
    # open profile: None/Anonymous; secure profile (ADR-0027): Basic256Sha256 SignAndEncrypt + user tokens
    await secure_server(server, security or OpcUaSecurity(), f"{space.namespace}:server")
    holder: list[Backplane] = []

    async def write(variable: str, value):
        return await holder[0].write(variable, value)

    plc = PlcAddressSpace(server, space, write)
    await plc.build()
    holder.append(Backplane(plc))
    link = await holder[0].serve(backplane_host, backplane_port)
    async with server, link:
        try:
            yield CommModule(server, plc, holder[0])
        finally:
            holder[0].close()  # else closing the backplane server waits for the CPU connection
