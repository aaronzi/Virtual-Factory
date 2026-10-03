"""CLI: build the static AAS and write the BaSyx preload directory (or upload to a running server).

    uv run -m provisioner build [--out infra/basyx/preload]
    uv run -m provisioner upload [--url http://localhost:8091]
    uv run -m provisioner check --data supplier --blueprints   # supplier environment (ADR-0028), port 8191
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import DATA_SETS, REPO, build, write_outputs
from .upload import upload

# per data set: preload directory, environment JSON, AAS environment
DEFAULTS = {"main": (REPO / "infra" / "basyx" / "preload", REPO / "aas" / "build" / "environment.json",
                     "http://localhost:8091"),
            "supplier": (REPO / "infra" / "basyx" / "preload-supplier",
                         REPO / "aas" / "build" / "supplier-environment.json", "http://localhost:8191")}


def main() -> int:
    parser = argparse.ArgumentParser(prog="provisioner", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "upload", "check"])
    parser.add_argument("--data", choices=sorted(DATA_SETS), default="main",
                        help="data set: main (aas/data, plant) or supplier (aas/data/supplier)")
    parser.add_argument("--out", type=Path, help="preload directory (default per data set)")
    parser.add_argument("--url", help="AAS environment for upload (default per data set)")
    parser.add_argument("--env-json", type=Path,
                        help="where to write the complete environment "
                             "(debugging; never into the preload dir)")
    parser.add_argument("--only", help="comma-separated asset tags (subset build for authoring)")
    parser.add_argument("--blueprints", action="store_true",
                        help="also validate aas/data/blueprints (check only)")
    args = parser.parse_args()
    if args.blueprints and args.command != "check":
        parser.error("--blueprints is only allowed with 'check' (blueprints are never preloaded)")
    out, env_json, url = DEFAULTS[args.data]
    result = build(only=set(args.only.split(",")) if args.only else None, blueprints=args.blueprints,
                   data_dir=DATA_SETS[args.data])
    report = result.builder.report
    env = result.environment
    print(f"{len(env['assetAdministrationShells'])} AAS, {len(env['submodels'])} submodels, "
          f"{len(env['conceptDescriptions'])} concept descriptions")
    for key, paths in sorted(report.unknown.items()):
        print(f"UNKNOWN  {key}: {', '.join(paths)}")
    for key, paths in sorted(report.missing.items()):
        print(f"MISSING  {key}: {len(paths)} mandatory values, e.g. {', '.join(paths[:3])}")
    if args.command == "build":
        for path in write_outputs(result, args.out or out, args.env_json or env_json):
            print(f"wrote {path}")
    elif args.command == "upload":
        upload(env, result.builder, args.url or url)
    return 1 if report.unknown else 0


if __name__ == "__main__":
    sys.exit(main())
