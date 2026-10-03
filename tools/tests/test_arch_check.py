import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "arch_check", Path(__file__).resolve().parent.parent / "arch_check.py")
arch_check = importlib.util.module_from_spec(_spec)
sys.modules["arch_check"] = arch_check
_spec.loader.exec_module(arch_check)

RULES = {
    "modules": {"core": [], "devices": ["core"], "factory": ["core", "devices"]},
    "isolated_submodules": ["devices"],
    "addons": {"mqtt": ["connectivity"], "gut": ["*tests*"]},
}


def test_allowed_and_forbidden_layers():
    assert arch_check.check_edge("devices/conveyor/a.gd", "core/fmi/b.gd", RULES) is None
    assert arch_check.check_edge("factory/main.tscn", "devices/conveyor/a.tscn", RULES) is None
    assert "must not depend" in arch_check.check_edge("core/fmi/b.gd", "devices/conveyor/a.gd", RULES)


def test_isolated_device_modules():
    assert arch_check.check_edge("devices/conveyor/a.gd", "devices/conveyor/view/b.gd", RULES) is None
    assert "isolated" in arch_check.check_edge("devices/ur5e/a.gd", "devices/conveyor/b.gd", RULES)


def test_addon_access():
    assert arch_check.check_edge("devices/x/a.gd", "addons/mqtt/mqtt.gd", RULES) is not None
    assert arch_check.check_edge("core/tests/test_a.gd", "addons/gut/test.gd", RULES) is None
