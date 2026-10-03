"""Executes LineControl operations as UNS commands to the line controller and waits for the acknowledgement
and, for PackML commands, for the resulting state (from the retained packml_state telemetry)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass

from vf_common.mqtt import MqttClient
from vf_common.uns import Uns, telemetry_value

from . import packml

log = logging.getLogger("ops-gateway")


@dataclass
class Result:
    accepted: bool
    message: str
    state: str = ""


class LineGateway:
    def __init__(self, mqtt: MqttClient, uns: Uns, controller: str = "PLC01", ack_timeout: float = 3.0,
                 state_timeout: float = 10.0):
        self.mqtt, self.uns, self.controller = mqtt, uns, controller
        self.ack_timeout, self.state_timeout = ack_timeout, state_timeout
        self.state: int | None = None
        self.history: list[int] = []  # recent states, so transient states (IDLE after Reset) are not missed
        self._history_base = 0        # absolute index of history[0]
        self._acks: dict[str, dict] = {}
        self._changed = threading.Condition()
        self._state_topic = uns.telemetry(controller, "packml_state")
        self._ack_prefix = uns.ack(controller, "")

    def start(self) -> None:
        self.mqtt.subscribe(self._state_topic, qos=0)
        self.mqtt.subscribe(self._ack_prefix + "+", qos=1)
        threading.Thread(target=self._consume, daemon=True, name="mqtt-consumer").start()

    # -- operations ----------------------------------------------------------------------------------

    def packml_command(self, command: str) -> Result:
        current = packml.state_name(self.state)
        reason = packml.check(command, current)
        if reason:
            return Result(False, reason, current)
        mark = self._history_base + len(self.history)
        ack = self._send("packml_command", packml.COMMANDS[command])
        if not ack.accepted:
            return Result(False, ack.message, current)
        target = packml.TARGET[command]
        reached = self._wait_for(lambda: target in self._states_since(mark), self.state_timeout)
        state = packml.state_name(self.state)
        if not reached:
            return Result(False, f"{command} sent, but state is {state} instead of {target}", state)
        return Result(True, f"{command} executed", state)

    def exchange_container(self, container: int) -> Result:
        if container not in (1, 2):
            return Result(False, f"unknown container {container} (1 = KLT A, 2 = KLT B)")
        return self._send("klt_exchange_command", container)

    def set_auto_exchange(self, enabled: bool) -> Result:
        return self._send("auto_exchange", bool(enabled))

    # -- MQTT ----------------------------------------------------------------------------------------

    def _send(self, variable: str, value) -> Result:
        corr = uuid.uuid4().hex[:12]
        self.mqtt.publish(self.uns.command(self.controller, variable),
                          {"v": value, "corr": corr, "source": "ops-gateway"}, qos=1)
        if not self._wait_for(lambda: corr in self._acks, self.ack_timeout):
            return Result(False, f"no acknowledgement from {self.controller} within {self.ack_timeout:.0f} s "
                                 "(is the factory simulation running?)")
        ack = self._acks.pop(corr)
        return Result(bool(ack.get("accepted")), ack.get("reason") or f"{variable} = {ack.get('v', value)}")

    def _record(self, state: int) -> None:
        self.state = state
        self.history.append(state)
        if len(self.history) > 500:
            self._history_base += 250
            self.history = self.history[250:]

    def _states_since(self, mark: int) -> list[str]:
        return [packml.state_name(s) for s in self.history[max(mark - self._history_base, 0):]]

    def _wait_for(self, predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._changed:
            while not predicate():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._changed.wait(remaining)
        return True

    def _consume(self) -> None:
        while True:
            msg = self.mqtt.get(timeout=1.0)
            if msg is None:
                continue
            with self._changed:
                if msg.topic == self._state_topic:
                    value = telemetry_value(msg.payload)
                    if isinstance(value, (int, float)):
                        self._record(int(value))
                elif msg.topic.startswith(self._ack_prefix):
                    ack = msg.json()
                    if isinstance(ack, dict) and ack.get("corr"):
                        self._acks[ack["corr"]] = ack
                self._changed.notify_all()
