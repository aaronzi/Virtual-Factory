#!/usr/bin/env python3
"""Complexity limits (CLAUDE.md): function length for GDScript (file and line length are enforced by gdlint,
godot/gdlintrc) and function, file and line length for the Python code in services/ and tools/.

A function body may have at most MAX_FUNCTION_LINES non-blank, non-comment lines, a Python file MAX_FILE_LINES
lines and a Python line MAX_LINE characters.
Exceptions: put `# complexity: allow <reason>` on the `func` / `def` line.

Usage: uv run tools/complexity_check.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "godot"
PYTHON_ROOTS = [REPO / "services", REPO / "tools"]
MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 300
MAX_LINE = 110
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


def check_python(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel = path.relative_to(REPO)
    problems = [f"{rel}:{n}: line has {len(line)} characters (max {MAX_LINE})"
                for n, line in enumerate(lines, 1) if len(line) > MAX_LINE]
    if len(lines) > MAX_FILE_LINES:
        problems.append(f"{rel}: {len(lines)} lines (max {MAX_FILE_LINES})")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = [ln for ln in lines[node.body[0].lineno - 1:node.end_lineno]
                    if ln.strip() and not ln.strip().startswith("#")]
            if len(body) > MAX_FUNCTION_LINES and "complexity: allow" not in lines[node.lineno - 1]:
                problems.append(f"{rel}:{node.lineno}: def {node.name} has {len(body)} lines "
                                f"(max {MAX_FUNCTION_LINES})")
    return problems


def main() -> int:
    files = [p for p in ROOT.rglob("*.gd") if not {"addons", ".godot"} & set(p.parts)]
    py_files = [p for root in PYTHON_ROOTS for p in root.rglob("*.py") if ".venv" not in p.parts]
    problems = [msg for f in sorted(files) for msg in check_file(f)]
    problems += [msg for f in sorted(py_files) for msg in check_python(f)]
    for msg in problems:
        print(msg)
    print(f"Complexity check: {len(files)} GDScript + {len(py_files)} Python files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
