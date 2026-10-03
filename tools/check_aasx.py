#!/usr/bin/env python3
"""Checks AASX packages with the IDTA aas-test-engines (metamodel V3.0, package structure, templates).

Usage: uv run tools/check_aasx.py [files...]
       (default: infra/basyx/preload/*.aasx and the supplier environment's preload-supplier/*.aasx)
"""

import sys
from pathlib import Path

from aas_test_engines import file as aas_file

PRELOADS = ("infra/basyx/preload", "infra/basyx/preload-supplier")
files = [Path(a) for a in sys.argv[1:]] or [p for d in PRELOADS for p in sorted(Path(d).glob("*.aasx"))]
failed = 0
for path in files:
    with open(path, "rb") as fh:
        result = aas_file.check_aasx_file(fh)
    print(f"{'OK  ' if result.ok() else 'FAIL'} {path.parent.name}/{path.name}")
    if not result.ok():
        failed += 1
        print("\n".join(line for line in result.to_lines() if "\x1b[91m" in line))
print(f"{len(files) - failed}/{len(files)} packages conformant")
sys.exit(1 if failed else 0)
