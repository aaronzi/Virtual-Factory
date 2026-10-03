#!/usr/bin/env python3
"""Architecture conformance check for the Godot project.

Builds the file-level dependency graph of all GDScript/scene files below godot/ and checks every
edge against docs/architecture/dependency-rules.yaml.

Detected references:
  * res:// paths in preload()/load()/extends/ext_resource
  * usages of global class names (class_name) declared in other files

Adherence = conformant edges / all edges (test code excluded). Documented exceptions are accepted
but still count as non-conformant. Exit code 1 on any undocumented violation or adherence < target.

Usage: uv run tools/arch_check.py [--verbose] [--json]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GODOT = ROOT / "godot"
RULES = ROOT / "docs" / "architecture" / "dependency-rules.yaml"

RES_PATH = re.compile(r'res://([\w\-./]+\.(?:gd|tscn|tres|scn|res|glb|gltf|xml|json))')
CLASS_NAME = re.compile(r"^class_name\s+(\w+)", re.MULTILINE)
COMMENT = re.compile(r"#.*$", re.MULTILINE)
STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


@dataclass
class Report:
    edges: list[tuple[str, str]] = field(default_factory=list)
    violations: list[tuple[str, str, str]] = field(default_factory=list)
    exceptions: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def adherence(self) -> float:
        bad = len(self.violations) + len(self.exceptions)
        return 1.0 if not self.edges else 1.0 - bad / len(self.edges)


def source_files() -> list[Path]:
    files = []
    for pattern in ("*.gd", "*.tscn", "*.tres"):
        files += [p for p in GODOT.rglob(pattern) if ".godot" not in p.parts]
    return sorted(files)


def rel(path: Path) -> str:
    return path.relative_to(GODOT).as_posix()


def module_of(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "<root>"


def submodule_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def is_test(path: str, rules: dict) -> bool:
    return any(d in path.split("/")[:-1] for d in rules.get("test_dirs", []))


def collect_classes(files: list[Path]) -> dict[str, str]:
    classes = {}
    for f in files:
        if f.suffix == ".gd":
            for name in CLASS_NAME.findall(f.read_text(encoding="utf-8", errors="ignore")):
                classes[name] = rel(f)
    return classes


def dependencies(f: Path, classes: dict[str, str]) -> set[str]:
    text = f.read_text(encoding="utf-8", errors="ignore")
    deps = set(RES_PATH.findall(text))
    if f.suffix == ".gd":
        code = STRING.sub('""', COMMENT.sub("", text))
        for word in set(re.findall(r"\b[A-Z]\w+\b", code)):
            if word in classes:
                deps.add(classes[word])
    deps.discard(rel(f))
    return deps


def check_edge(src: str, dst: str, rules: dict) -> str | None:
    """Returns a violation message or None if the edge is allowed."""
    src_mod, dst_mod = module_of(src), module_of(dst)
    if dst_mod == "addons":
        addon = dst.split("/")[1]
        allowed = rules.get("addons", {}).get(addon, [])
        if src_mod == "addons" or any(fnmatch.fnmatch(src, p) or src_mod == p for p in allowed):
            return None
        return f"addon '{addon}' not allowed for module '{src_mod}'"
    if src_mod in ("addons", "<root>"):
        return None
    if src_mod == dst_mod:
        if src_mod in rules.get("isolated_submodules", []) and submodule_of(src) != submodule_of(dst):
            return f"isolated submodules: {submodule_of(src)} -> {submodule_of(dst)}"
        return None
    if dst_mod == "<root>":
        return None
    allowed = rules.get("modules", {}).get(src_mod)
    if allowed is None:
        return f"unknown module '{src_mod}' (add it to dependency-rules.yaml)"
    if dst_mod not in allowed:
        return f"module '{src_mod}' must not depend on '{dst_mod}'"
    return None


def is_exception(src: str, dst: str, rules: dict) -> dict | None:
    for exc in rules.get("exceptions") or []:
        if fnmatch.fnmatch(src, exc["from"]) and fnmatch.fnmatch(dst, exc["to"]):
            return exc
    return None


def run(rules: dict) -> Report:
    files = source_files()
    classes = collect_classes(files)
    report = Report()
    for f in files:
        src = rel(f)
        if is_test(src, rules) or module_of(src) == "addons":
            continue
        for dst in sorted(dependencies(f, classes)):
            report.edges.append((src, dst))
            problem = check_edge(src, dst, rules)
            if problem is None:
                continue
            exc = is_exception(src, dst, rules)
            if exc:
                report.exceptions.append((src, dst, exc.get("adr", exc.get("reason", ""))))
            else:
                report.violations.append((src, dst, problem))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true", help="print all edges")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    rules = yaml.safe_load(RULES.read_text())
    report = run(rules)
    target = float(rules.get("target_adherence", 0.95))
    if args.json:
        print(json.dumps({"adherence": report.adherence, "edges": len(report.edges),
                          "violations": report.violations, "exceptions": report.exceptions}, indent=2))
    else:
        if args.verbose:
            for src, dst in report.edges:
                print(f"  {src} -> {dst}")
        for src, dst, why in report.exceptions:
            print(f"EXCEPTION  {src} -> {dst}  ({why})")
        for src, dst, why in report.violations:
            print(f"VIOLATION  {src} -> {dst}  [{why}]")
        conformant = len(report.edges) - len(report.violations) - len(report.exceptions)
        print(f"Architecture adherence: {report.adherence:.1%} "
              f"({conformant}/{len(report.edges)} edges conformant, "
              f"{len(report.exceptions)} documented exceptions, "
              f"{len(report.violations)} violations, target {target:.0%})")
    return 0 if not report.violations and report.adherence >= target else 1


if __name__ == "__main__":
    sys.exit(main())
