"""PackML (ISA-TR88.00.02) numbers shared by the services: unit states (index = number, as in the controller
godot/core/plc/packml_state_machine.gd), commands and unit modes."""

from __future__ import annotations

STATES = ["UNDEFINED", "CLEARING", "STOPPED", "STARTING", "IDLE", "SUSPENDED", "EXECUTE", "STOPPING",
          "ABORTING", "ABORTED", "HOLDING", "HELD", "UNHOLDING", "SUSPENDING", "UNSUSPENDING", "RESETTING",
          "COMPLETING", "COMPLETE"]
COMMANDS = {"Reset": 1, "Start": 2, "Stop": 3, "Hold": 4, "Unhold": 5, "Suspend": 6, "Unsuspend": 7,
            "Abort": 8, "Clear": 9}
# unit modes of the line controller (ISA-TR88: 1 Production, 2 Maintenance, 3 Manual)
UNIT_MODES = {"Production": 1, "Maintenance": 2, "Manual": 3}
# the line controller accepts a unit mode change only in these wait states
# (godot/control/sorting_line/unit_mode.gd)
UNIT_MODE_CHANGE_STATES = {"STOPPED", "IDLE", "ABORTED"}


def state_name(number: int | None) -> str:
    return STATES[number] if number is not None and 0 <= number < len(STATES) else "UNKNOWN"


def unit_mode_name(number: int | None) -> str:
    return next((name for name, n in UNIT_MODES.items() if n == number), "UNKNOWN")
