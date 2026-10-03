"""OPC UA path of the ops gateway (ADR-0024): Control Component endpoints whose AID affordance belongs to an
OPC UA interface are executed as method calls (actions) and observed as monitored items (properties). The
sessions run in a background asyncio loop; the gateway threads use the blocking call()/configure().

A method call is synchronous: Good = the controller's CPU took the command, a bad status code is the
rejection reason (BadNotConnected: the CPU of the PLC is not linked to its communication module, ...)."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from asyncua import ua

from vf_common.aid import Affordance
from vf_common.opcua_client import UaSession, endpoint_map, rewrite, status_text

log = logging.getLogger("ops-gateway")


class OpcUaLink:
    def __init__(self, on_value: Callable[[str, object], None], call_timeout: float = 3.0,
                 sampling_ms: float = 0.0, publishing_ms: float = 50.0,
                 mapping: dict[str, str] | None = None):
        self.on_value, self.call_timeout = on_value, call_timeout
        self.sampling_ms, self.publishing_ms = sampling_ms, publishing_ms
        self.mapping = endpoint_map() if mapping is None else mapping
        self.loop = asyncio.new_event_loop()
        self.sessions: dict[str, UaSession] = {}
        self._subscriptions: dict[str, object] = {}  # server endpoint -> asyncua subscription
        self._tasks: set[asyncio.Future] = set()

    def start(self) -> None:
        threading.Thread(target=self.loop.run_forever, daemon=True, name="opcua-loop").start()

    def configure(self, properties: dict[str, Affordance]) -> None:
        """Observes the given property endpoints (others are dropped); returns at once, subscribing runs in
        the background until the servers answer."""
        asyncio.run_coroutine_threadsafe(self._configure(dict(properties)), self.loop)

    def call(self, action: Affordance, value) -> tuple[bool, str]:
        future = asyncio.run_coroutine_threadsafe(self._call(action, value), self.loop)
        try:
            return future.result(self.call_timeout + 1.0)
        except TimeoutError:
            future.cancel()
            return False, f"no answer from {action.base} within {self.call_timeout:.0f} s"

    # -- event loop side -----------------------------------------------------------------------------

    def _session(self, base: str) -> UaSession:
        endpoint = rewrite(base, self.mapping)
        if endpoint not in self.sessions:
            self.sessions[endpoint] = UaSession(endpoint, request_timeout=self.call_timeout)
        return self.sessions[endpoint]

    async def _call(self, action: Affordance, value) -> tuple[bool, str]:
        session = self._session(action.base)
        if not session.connected:
            try:
                await asyncio.wait_for(session.connect(retry_s=1.0), self.call_timeout)
            except TimeoutError:
                return False, f"OPC UA server {session.endpoint} not reachable"
        try:
            await asyncio.wait_for(session.call(action.form.topic, [value]), self.call_timeout)
        except ua.UaStatusCodeError as exc:
            return False, f"{action.name}({value!r}) rejected by {session.endpoint}: {status_text(exc)}"
        except (ValueError, OSError, TimeoutError, ua.UaError) as exc:
            return False, f"{action.name}({value!r}) failed: {status_text(exc)}"
        return True, f"{action.name}({value!r}) called on {session.endpoint}"

    async def _configure(self, properties: dict[str, Affordance]) -> None:
        for task in list(self._tasks):  # observers still waiting for a server of the old configuration
            task.cancel()
        for endpoint, subscription in list(self._subscriptions.items()):
            await subscription.delete()
            del self._subscriptions[endpoint]
        by_server: dict[str, list[tuple[str, Affordance]]] = {}
        for name, aff in properties.items():
            by_server.setdefault(aff.base, []).append((name, aff))
        for base, entries in by_server.items():
            task = asyncio.ensure_future(self._observe(base, entries))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _observe(self, base: str, entries: list[tuple[str, Affordance]]) -> None:
        session = self._session(base)
        await session.connect()
        handler = _Handler(self.on_value)
        subscription = await session.client.create_subscription(self.publishing_ms, handler)
        for name, aff in entries:
            node = await session.node(aff.form.topic)
            handler.names[node.nodeid] = name
            await subscription.subscribe_data_change(node, sampling_interval=self.sampling_ms, queuesize=50)
        self._subscriptions[session.endpoint] = subscription
        log.info("observing %s on %s", ", ".join(n for n, _ in entries), session.endpoint)


class _Handler:
    """asyncua subscription handler: forwards good values as (endpoint name, value)."""

    def __init__(self, on_value: Callable[[str, object], None]):
        self.on_value = on_value
        self.names: dict[ua.NodeId, str] = {}

    def datachange_notification(self, node, value, data) -> None:
        status = data.monitored_item.Value.StatusCode
        if status is not None and not status.is_good():
            return
        name = self.names.get(node.nodeid)
        if name is not None:
            self.on_value(name, value)
