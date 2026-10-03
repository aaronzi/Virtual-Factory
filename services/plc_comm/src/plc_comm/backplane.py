"""Backplane link between the simulated PLC CPU (Godot, godot/connectivity/plc_link) and this communication
module: newline-delimited JSON over TCP, the CPU connects (docs/interfaces/uns.md, "Backplane").

    CPU -> module  {"type": "hello", "protocol": 1, "device", "model", "session"}
                   (after the welcome:)
                   {"type": "image", "ts", "values": {variable: value}}     changed values, all first
                   {"type": "event", "event", "ts", "payload": {...}}       UNS event payload of the CPU
                   {"type": "result", "id", "accepted", "reason", "v"}      answer to a write
    module -> CPU  {"type": "welcome", "endpoint", "namespace"}
                   {"type": "write", "id", "variable", "v"}                 applied between two PLC cycles

One CPU at a time: a new connection replaces the previous one."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from datetime import datetime

from .address_space import PlcAddressSpace

log = logging.getLogger("plc-comm")
PROTOCOL = 1


def parse_ts(value) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


class Backplane:
    def __init__(self, plc: PlcAddressSpace, write_timeout: float = 2.0):
        self.plc, self.write_timeout = plc, write_timeout
        self.instance = plc.space.instance
        self.stats = {"images": 0, "events": 0, "writes": 0, "write_ms": 0.0}
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def serve(self, host: str, port: int) -> asyncio.Server:
        server = await asyncio.start_server(self._handle, host, port, limit=1 << 20)
        log.info("backplane listening on %s:%d (CPU of %s)", host, port, self.instance)
        return server

    def close(self) -> None:
        """Drops the CPU connection (shutdown)."""
        if self._writer is not None:
            self._writer.close()

    async def write(self, variable: str, value) -> tuple[bool, str]:
        """Sends a write to the CPU and waits for its result."""
        writer = self._writer
        if writer is None:
            raise ConnectionError(f"CPU of {self.instance} not connected")
        request_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        start = time.perf_counter()
        try:
            self._send(writer, {"type": "write", "id": request_id, "variable": variable, "v": value})
            await writer.drain()
            result = await asyncio.wait_for(future, self.write_timeout)
        finally:
            self._pending.pop(request_id, None)
        self.stats["writes"] += 1
        self.stats["write_ms"] += (time.perf_counter() - start) * 1000.0
        return bool(result.get("accepted")), str(result.get("reason") or "")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        if self._writer is not None:
            log.warning("new CPU connection from %s replaces the previous one", peer)
            self._writer.close()
        self._writer = writer
        log.info("CPU connected from %s", peer)
        try:
            while line := await reader.readline():
                await self._dispatch(json.loads(line), writer)
        except (ConnectionError, ValueError, asyncio.LimitOverrunError) as exc:
            log.warning("backplane connection from %s failed: %s", peer, exc)
        finally:
            if self._writer is writer:
                self._writer = None
                await self.plc.set_connected(False)
                for future in self._pending.values():
                    future.cancel()
                log.info("CPU disconnected (%s)", peer)
            writer.close()

    async def _dispatch(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        kind = msg.get("type")
        if kind == "image":
            await self.plc.update(msg.get("values") or {}, parse_ts(msg.get("ts")))
            self.stats["images"] += 1
        elif kind == "event":
            if await self.plc.fire(msg.get("event", ""), msg.get("payload") or {}, parse_ts(msg.get("ts"))):
                self.stats["events"] += 1
        elif kind == "result":
            future = self._pending.get(msg.get("id"))
            if future is not None and not future.done():
                future.set_result(msg)
        elif kind == "hello":
            await self._hello(msg, writer)

    async def _hello(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        if msg.get("device") != self.instance or msg.get("protocol") != PROTOCOL:
            log.error("CPU hello for %s (protocol %s) does not match %s (protocol %d): closing",
                      msg.get("device"), msg.get("protocol"), self.instance, PROTOCOL)
            writer.close()
            return
        log.info("CPU %s (%s) online, session %s", msg.get("device"), msg.get("model"), msg.get("session"))
        await self.plc.set_connected(True, str(msg.get("session") or ""))
        self._send(writer, {"type": "welcome", "endpoint": self.plc.space.endpoint,
                            "namespace": self.plc.space.namespace})

    @staticmethod
    def _send(writer: asyncio.StreamWriter, msg: dict) -> None:
        writer.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
