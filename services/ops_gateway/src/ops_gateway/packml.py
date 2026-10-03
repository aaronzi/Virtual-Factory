"""PackML unit state model (ISA-TR88.00.02) as seen from outside the controller: which command is allowed in
which state and which state it finally leads to. Numbers match the controller
(godot/core/plc/packml_state_machine.gd)."""

from __future__ import annotations

from vf_common.packml import COMMANDS, STATES, state_name  # noqa: F401 - re-exported

_STOPPABLE = {"IDLE", "STARTING", "EXECUTE", "HOLDING", "HELD", "UNHOLDING", "SUSPENDING", "SUSPENDED",
              "UNSUSPENDING", "RESETTING", "COMPLETING", "COMPLETE"}
ALLOWED = {
    "Reset": {"STOPPED", "COMPLETE"}, "Start": {"IDLE"}, "Stop": _STOPPABLE, "Hold": {"EXECUTE"},
    "Unhold": {"HELD"}, "Suspend": {"EXECUTE"}, "Unsuspend": {"SUSPENDED"},
    "Abort": set(STATES) - {"ABORTING", "ABORTED"}, "Clear": {"ABORTED"},
}
# final (wait) state reached after the acting state;
# Suspend/Unsuspend may also be issued by the controller itself
TARGET = {"Reset": "IDLE", "Start": "EXECUTE", "Stop": "STOPPED", "Hold": "HELD", "Unhold": "EXECUTE",
          "Suspend": "SUSPENDED", "Unsuspend": "EXECUTE", "Abort": "ABORTED", "Clear": "STOPPED"}


def check(command: str, state: str) -> str | None:
    """None if the command is allowed in the state, otherwise the rejection reason."""
    if command not in COMMANDS:
        return f"unknown command '{command}' (one of {', '.join(COMMANDS)})"
    if state not in ALLOWED[command]:
        allowed = sorted(c for c, states in ALLOWED.items() if state in states)
        return f"{command} is not allowed in state {state} (allowed: {', '.join(allowed) or 'none'})"
    return None
