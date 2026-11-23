#!/usr/bin/env python3
"""Copy the static console. Does not upload it and does not include config.js."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "management" / "ui"
INCLUDE = ("index.html", "styles.css", "app.js", "auth.js", "build.js")


def build(destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in INCLUDE:
        shutil.copy2(UI / name, destination / name)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Package the static console. No upload.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    print(build(Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
