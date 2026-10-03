"""Test helper: a scripted stand-in for the simulated PLC CPU on the backplane (the real one is Godot,
godot/connectivity/plc_link). It sends hello and the process image, walks PackML states on packml_command
and applies unit mode requests like the controller (only in STOPPED, IDLE, ABORTED). Used by the tests of
plc_comm, edge and ops gateway."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from vf_common.packml import COMMANDS, STATES, UNIT_MODE_CHANGE_STATES

FINAL = {"Reset": "IDLE", "Start": "EXECUTE", "Stop": "STOPPED", "Hold": "HELD", "Unhold": "EXECUTE",
         "Suspend": "SUSPENDED", "Unsuspend": "EXECUTE", "Abort": "ABORTED", "Clear": "STOPPED"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FakeCpu:
    def __init__(self, device: str = "PLC01", session: str = "S-test", state: str = "EXECUTE",
                 accept: bool = True):
        self.device, self.session, self.accept = device, session, accept
        self.image = {"packml_state": STATES.index(state), "unit_mode": 1, "parts_total": 0, "parts_ok": 0,
                      "auto_exchange": True, "cv_run": True, "belt_speed": 0.25}
        self.writes: list[tuple[str, object]] = []
        self.seq = 0
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None

    async def connect(self, host: str, port: int) -> None:
        reader, self._writer = await asyncio.open_connection(host, port)
        self._send({"type": "hello", "protocol": 1, "device": self.device, "session": self.session,
                    "model": "SortingLinePLC"})
        self._send({"type": "image", "ts": now_iso(), "values": self.image})
        await self._writer.drain()
        self._task = asyncio.create_task(self._serve(reader))

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
        if self._writer:
            self._writer.close()

    async def set(self, **values) -> None:
        self.image.update(values)
        self._send({"type": "image", "ts": now_iso(), "values": values})
        await self._writer.drain()

    async def event(self, event: str, **fields) -> None:
        self.seq += 1
        payload = {"event": event, "device": self.device, "session": self.session, "seq": self.seq,
                   "ts": now_iso(), **fields}
        self._send({"type": "event", "event": event, "ts": payload["ts"], "payload": payload})
        await self._writer.drain()

    async def _serve(self, reader: asyncio.StreamReader) -> None:
        while line := await reader.readline():
            msg = json.loads(line)
            if msg.get("type") == "write":
                await self._write(msg)

    async def _write(self, msg: dict) -> None:
        variable, value = msg["variable"], msg["v"]
        self.writes.append((variable, value))
        self._send({"type": "result", "id": msg["id"], "accepted": self.accept,
                    "reason": "" if self.accept else "rejected by the FMU",
                    "v": value if self.accept else None})
        if not self.accept:
            await self._writer.drain()
            return
        await asyncio.sleep(0.02)  # the next PLC cycles
        state = STATES[self.image["packml_state"]]
        if variable == "packml_command":
            name = next((k for k, v in COMMANDS.items() if v == value), None)
            if name:
                await self.set(packml_state=STATES.index(FINAL[name]))
        elif variable == "unit_mode_command":
            if state in UNIT_MODE_CHANGE_STATES and value in (1, 2, 3):
                await self.set(unit_mode=value)
        else:
            await self.set(**{variable: value})

    def _send(self, msg: dict) -> None:
        self._writer.write(json.dumps(msg).encode() + b"\n")
