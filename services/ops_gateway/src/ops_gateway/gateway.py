"""Executes LineControl operations as commands to the line controller and waits for the acknowledgement and,
for PackML commands, for the resulting state.

Topics, QoS/retain flags and payload keys are not configured here: they come from the AAS (`ControlConfig`,
resolved via Control Component endpoints -> AID, see control.py). Until a configuration has been resolved,
every operation is rejected - there is deliberately no fallback to the UNS registry (ADR-0020)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from vf_common.mqtt import Message, MqttClient
from vf_common.uns import telemetry_value

from . import packml
from .control import AUTO_EXCHANGE, PACKML, STATE, ControlConfig

log = logging.getLogger("ops-gateway")
NOT_CONFIGURED = "ops gateway not configured: endpoints not yet resolved from the AAS (see gateway log)"


@dataclass
class Result:
    accepted: bool
    message: str
    state: str = ""


class LineGateway:
    def __init__(self, mqtt: MqttClient, config: ControlConfig | None = None, ack_timeout: float = 3.0,
                 state_timeout: float = 10.0, source: str = "ops-gateway"):
        self.mqtt, self.source = mqtt, source
        self.ack_timeout, self.state_timeout = ack_timeout, state_timeout
        self.config: ControlConfig | None = None
        self.state: int | None = None
        self.history: list[int] = []  # recent states, so transient states (IDLE after Reset) are not missed
        self._history_base = 0        # absolute index of history[0]
        self._acks: dict[str, dict] = {}
        self._changed = threading.Condition()
        self._subscribed: dict[str, int] = {}
        self.on_other: Callable[[Message], None] | None = None  # messages on other topics (AAS events)
        if config:
            self.configure(config)

    def start(self) -> None:
        threading.Thread(target=self._consume, daemon=True, name="mqtt-consumer").start()

    def configure(self, config: ControlConfig) -> None:
        """(Re)configures topics; subscriptions follow the AID forms (state property, ack forms)."""
        topics = {a.form.topic: a.form.qos for a in config.endpoints.values() if a.kind == "property"}
        topics |= {a.ack.topic: a.ack.qos for a in config.endpoints.values() if a.ack}
        with self._changed:
            for topic in set(self._subscribed) - set(topics):
                self.mqtt.unsubscribe(topic)
            for topic, qos in topics.items():
                if topic not in self._subscribed:
                    self.mqtt.subscribe(topic, qos=qos)
            self._subscribed, self.config = topics, config
        log.info("configured from the AAS (controller %s):\n  %s", config.controller,
                 "\n  ".join(config.describe()))

    # -- operations ----------------------------------------------------------------------------------

    def packml_command(self, command: str) -> Result:
        if self.config is None:
            return Result(False, NOT_CONFIGURED)
        current = packml.state_name(self.state)
        reason = packml.check(command, current)
        if reason:
            return Result(False, reason, current)
        mark = self._history_base + len(self.history)
        ack = self.send(PACKML, packml.COMMANDS[command])
        if not ack.accepted:
            return Result(False, ack.message, current)
        target = packml.TARGET[command]
        reached = self._wait_for(lambda: target in self._states_since(mark), self.state_timeout)
        state = packml.state_name(self.state)
        if not reached:
            return Result(False, f"{command} sent, but state is {state} instead of {target}", state)
        return Result(True, f"{command} executed", state)

    def set_auto_exchange(self, enabled: bool) -> Result:
        return self.send(AUTO_EXCHANGE, bool(enabled))

    def wait_state(self, predicate: Callable[[str], bool], timeout: float) -> bool:
        return self._wait_for(lambda: predicate(packml.state_name(self.state)), timeout)

    # -- MQTT ----------------------------------------------------------------------------------------

    def send(self, endpoint: str, value) -> Result:
        """Publishes a command on the AID action behind a Control Component endpoint and waits for its ack."""
        config = self.config
        if config is None:
            return Result(False, NOT_CONFIGURED)
        action = config.endpoints.get(endpoint)
        if action is None or action.kind != "action":
            return Result(False, f"{config.controller}/ControlComponentInstance has no command endpoint "
                                 f"{endpoint}")
        corr = uuid.uuid4().hex[:12]
        payload = {action.key("Value", "v"): value, action.key("CorrelationId", "corr"): corr,
                   action.key("Source", "source"): self.source}
        self.mqtt.publish(action.form.topic, payload, qos=action.form.qos, retain=action.form.retain)
        if action.ack is None:
            return Result(True, f"{action.name} = {value} sent (the AID describes no acknowledgement)")
        if not self._wait_for(lambda: corr in self._acks, self.ack_timeout):
            return Result(False, f"no acknowledgement from {config.controller} on {action.ack.topic} within "
                                 f"{self.ack_timeout:.0f} s (is the factory simulation running?)")
        ack = self._acks.pop(corr)
        accepted = ack.get(action.ack_key("Accepted", "accepted"))
        reason = ack.get(action.ack_key("Reason", "reason"))
        applied = ack.get(action.ack_key("Value", "v"), value)
        return Result(bool(accepted), reason or f"{action.name} = {applied}")

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
                handled = self._dispatch(msg)
                self._changed.notify_all()
            if not handled and self.on_other:
                self.on_other(msg)

    def _dispatch(self, msg: Message) -> bool:
        config = self.config
        if config is None:
            return False
        state = config.endpoints.get(STATE)
        if state and msg.topic == state.form.topic:
            value = telemetry_value(msg.payload, state.key("Value", "v"))
            if isinstance(value, (int, float)):
                self._record(int(value))
            return True
        action = next((a for a in config.endpoints.values() if a.ack and a.ack.topic == msg.topic), None)
        if action is None:
            return False
        ack = msg.json()
        corr_key = action.ack_key("CorrelationId", "corr")
        if isinstance(ack, dict) and ack.get(corr_key):
            self._acks[ack[corr_key]] = ack
        return True

