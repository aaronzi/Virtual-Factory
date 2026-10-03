"""Unit tests of the CI integration helper (tools/ci_integration.py): skip check and readiness gate."""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ci_integration", Path(__file__).resolve().parent.parent / "ci_integration.py")
ci = importlib.util.module_from_spec(_spec)
sys.modules["ci_integration"] = ci
_spec.loader.exec_module(ci)

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="3">
<testcase classname="services.erp.tests.test_erp_integration" name="test_order" time="1"/>
<testcase classname="services.mes.tests.test_dpp_integration" name="test_retention" time="0">
<skipped type="pytest.skip" message="no shipped part from an earlier session">skip</skipped></testcase>
<testcase classname="tools.tests.test_grafana_integration" name="test_health" time="0"/>
</testsuite></testsuites>"""


def _report(tmp_path: Path, text: str = JUNIT) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_skip_fails_the_run(tmp_path, capsys):
    assert ci.check_skips(_report(tmp_path), []) == 1
    assert "test_dpp_integration::test_retention: no shipped part" in capsys.readouterr().out


def test_allowed_skips_pass(tmp_path):
    assert ci.check_skips(_report(tmp_path), ["test_dpp_integration::test_retention"]) == 0


def test_no_tests_fails(tmp_path):
    assert ci.check_skips(_report(tmp_path, "<testsuites><testsuite/></testsuites>"), []) == 1


def test_gate_retries_until_checks_pass_and_reports_failures(capsys):
    calls = []

    def eventually() -> str | None:
        calls.append(1)
        return None if len(calls) >= 2 else "not yet"

    assert ci.gate({"eventually": eventually}, timeout_s=5, step_s=0.01)
    assert not ci.gate({"never": lambda: "still missing", "boom": lambda: 1 / 0}, timeout_s=0.05,
                       step_s=0.01)
    out = capsys.readouterr().out
    assert "FAILED  never: still missing" in out and "ZeroDivisionError" in out
