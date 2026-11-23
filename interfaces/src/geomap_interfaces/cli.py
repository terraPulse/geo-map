"""Offline registry commands. This CLI does not serve traffic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import RegistryError
from .legacy import import_legacy_tree
from .registry import load_registry, registry_to_obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geomap-interfaces", description="Validate or import a geo-map dataset registry.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="load a registry JSON file and report dataset ids")
    validate.add_argument("path")
    legacy = sub.add_parser("import-legacy", help="import local setting.ini files to registry JSON on stdout")
    legacy.add_argument("root")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            registry = load_registry(Path(args.path))
            json.dump({"schema": registry.schema, "ids": [item.id for item in registry.datasets]}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        registry = import_legacy_tree(Path(args.root))
        json.dump(registry_to_obj(registry), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except (RegistryError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"geomap-interfaces: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
