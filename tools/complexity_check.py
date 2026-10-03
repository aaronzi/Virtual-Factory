#!/usr/bin/env python3
"""Complexity limits for GDScript that gdlint does not cover: function length.

A function body may have at most MAX_FUNCTION_LINES non-blank, non-comment lines.
Exceptions: put `# complexity: allow <reason>` on the `func` line.
File length and line length are enforced by gdlint (godot/gdlintrc).

Usage: uv run tools/complexity_check.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "godot"
MAX_FUNCTION_LINES = 40
FUNC = re.compile(r"^(\s*)(static\s+)?func\s+(\w+)")


def check_file(path: Path) -> list[str]:
    problems = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = FUNC.match(lines[i])
        if not m:
            i += 1
            continue
        indent, name, allowed = len(m.group(1)), m.group(3), "complexity: allow" in lines[i]
        start, body = i + 1, 0
        i += 1
        while i < len(lines):
            stripped = lines[i].strip()
            line_indent = len(lines[i]) - len(lines[i].lstrip())
            if stripped and line_indent <= indent and not stripped.startswith((")", "#")):
                break
            if stripped and not stripped.startswith("#"):
                body += 1
            i += 1
        if body > MAX_FUNCTION_LINES and not allowed:
            problems.append(f"{path.relative_to(ROOT)}:{start}: func {name} has {body} lines "
                            f"(max {MAX_FUNCTION_LINES})")
    return problems


def main() -> int:
    files = [p for p in ROOT.rglob("*.gd") if not {"addons", ".godot"} & set(p.parts)]
    problems = [msg for f in sorted(files) for msg in check_file(f)]
    for msg in problems:
        print(msg)
    print(f"Complexity check: {len(files)} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
