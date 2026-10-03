"""OPC UA client helpers for services configured from AID OPC UA forms (ADR-0024): one session per server
endpoint (asyncua, automatic reconnect with subscription re-creation), nodes resolved from AID hrefs
(`?id=nsu=<uri>;s=<identifier>`), method calls on the parent object with typed arguments.

Endpoint rewriting: the AID describes the server as seen from the host (opc.tcp://localhost:4840/...); inside
the compose network the services use VF_OPCUA_ENDPOINTS="opc.tcp://localhost:4840=opc.tcp://plc-comm:4840"
(comma-separated prefix replacements)."""

from __future__ import annotations

import asyncio
import logging
import os

from asyncua import Client, Node, ua
from asyncua.ua.status_codes import get_name_and_doc

from .opcua_plc import parse_href

log = logging.getLogger(__name__)
_ARG_TYPES = {ua.VariantType.Double: float, ua.VariantType.Float: float, ua.VariantType.Int32: int,
              ua.VariantType.Int64: int, ua.VariantType.UInt64: int, ua.VariantType.Boolean: bool,
              ua.VariantType.String: str}


def endpoint_map(raw: str | None = None) -> dict[str, str]:
    raw = os.environ.get("VF_OPCUA_ENDPOINTS", "") if raw is None else raw
    pairs = [p.split("=", 1) for p in raw.split(",") if "=" in p]
    return {a.strip(): b.strip() for a, b in pairs}


def rewrite(endpoint: str, mapping: dict[str, str]) -> str:
    for prefix, target in mapping.items():
        if endpoint.startswith(prefix):
            return target + endpoint[len(prefix):]
    return endpoint


def status_text(exc: BaseException) -> str:
    """'BadNotConnected: <doc>' for OPC UA status errors, else the exception text."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        name, doc = get_name_and_doc(code)
        return f"{name}: {doc.rstrip('.')}" if doc else name
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def typed_argument(argument: ua.Argument, value) -> ua.Variant:
    """Converts a JSON value to the method argument's data type (builtin types only)."""
    vtype = ua.VariantType(argument.DataType.Identifier) if argument.DataType.NamespaceIndex == 0 \
        else ua.VariantType.Variant
    convert = _ARG_TYPES.get(vtype)
    if convert is bool and not isinstance(value, bool):
        if value not in (0, 1, "0", "1", "true", "false"):
            raise ValueError(f"{argument.Name}: {value!r} is not a boolean")
        value = str(value).lower() in ("1", "true")
    elif convert is int and isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{argument.Name}: {value!r} is not an integer")
    return ua.Variant(convert(value) if convert else value, vtype)


class UaSession:
    """Client session to one server endpoint; nodes, method parents and argument types are cached."""

    def __init__(self, endpoint: str, timeout: float = 4.0, request_timeout: float = 3.0):
        self.endpoint = endpoint
        self.client = Client(endpoint, timeout=timeout, auto_reconnect=True,
                             reconnect_max_delay=10.0, reconnect_request_timeout=request_timeout)
        self.client.name = self.client.description = "Virtual Factory service"
        self.connected = False
        self._namespaces: dict[str, int] = {}
        self._methods: dict[str, tuple[Node, Node, list[ua.Argument]]] = {}
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()

    async def connect(self, retry_s: float = 5.0) -> None:
        """Connects, retrying until the server answers (the client reconnects by itself afterwards)."""
        async with self._connect_lock:
            while not self.connected:
                try:
                    await self.client.connect()
                    self.connected = True
                    log.info("OPC UA session to %s established", self.endpoint)
                except (OSError, asyncio.TimeoutError, ua.UaError) as exc:
                    log.warning("OPC UA server %s not reachable (%s), retrying in %.0f s", self.endpoint,
                                status_text(exc), retry_s)
                    await asyncio.sleep(retry_s)

    async def close(self) -> None:
        if self.connected:
            self.connected = False
            await self.client.disconnect()

    async def node(self, href: str) -> Node:
        namespace, identifier = parse_href(href)
        if namespace not in self._namespaces:
            self._namespaces[namespace] = await self.client.get_namespace_index(namespace)
        return self.client.get_node(ua.NodeId(identifier, self._namespaces[namespace]))

    async def call(self, href: str, values: list) -> None:
        """Calls the method behind `href` on its parent object; raises ua.UaStatusCodeError when the server
        answers with a bad status, ValueError when an argument does not fit."""
        async with self._lock:
            if href not in self._methods:
                method = await self.node(href)
                arguments = []
                inputs = await method.get_children(refs=ua.ObjectIds.HasProperty)
                for prop in inputs:
                    if (await prop.read_browse_name()).Name == "InputArguments":
                        arguments = await prop.read_value() or []
                self._methods[href] = (await method.get_parent(), method, arguments)
        parent, method, arguments = self._methods[href]
        if len(values) != len(arguments):
            raise ValueError(f"method expects {len(arguments)} argument(s), got {len(values)}")
        await parent.call_method(method, *[typed_argument(a, v) for a, v in zip(arguments, values)])
