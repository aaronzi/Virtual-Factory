"""CLI: build the static AAS and write the BaSyx preload directory (or upload to a running server).

    uv run -m provisioner build [--out infra/basyx/preload]
    uv run -m provisioner upload [--url http://localhost:8091]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import REPO, build, write_outputs
from .upload import upload


def main() -> int:
    parser = argparse.ArgumentParser(prog="provisioner", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "upload", "check"])
    parser.add_argument("--out", type=Path, default=REPO / "infra" / "basyx" / "preload")
    parser.add_argument("--url", default="http://localhost:8091")
    parser.add_argument("--only", help="comma-separated asset tags (subset build for authoring)")
    args = parser.parse_args()
    result = build(only=set(args.only.split(",")) if args.only else None)
    report = result.builder.report
    env = result.environment
    print(f"{len(env['assetAdministrationShells'])} AAS, {len(env['submodels'])} submodels, "
          f"{len(env['conceptDescriptions'])} concept descriptions")
    for key, paths in sorted(report.unknown.items()):
        print(f"UNKNOWN  {key}: {', '.join(paths)}")
    for key, paths in sorted(report.missing.items()):
        print(f"MISSING  {key}: {len(paths)} mandatory values, e.g. {', '.join(paths[:3])}")
    if args.command == "build":
        for path in write_outputs(result, args.out):
            print(f"wrote {path.relative_to(REPO)}")
    elif args.command == "upload":
        upload(env, result.builder, args.url)
    return 1 if report.unknown else 0


if __name__ == "__main__":
    sys.exit(main())
