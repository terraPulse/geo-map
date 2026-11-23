#!/usr/bin/env python3
"""Build the Lambda zip. Does not upload it and does not call AWS."""

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "management" / "src"
FIXTURES = ROOT / "management" / "fixtures" / "synthetic_layers.json"


def build(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (SRC / "layer_manager").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            archive.write(path, path.relative_to(SRC).as_posix())
        archive.write(SRC / "layer_manager_lambda.py", "layer_manager_lambda.py")
        archive.write(FIXTURES, "layer_manager/synthetic_fixtures.json")
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Package the layer-manager Lambda. No upload.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    path = build(Path(args.out))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
