"""Include redistributable Builder dependency license texts in the Admin ZIP.

The authoring process uses installed wheels; copying their own license files
avoids reconstructing license notices from potentially stale web pages.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import shutil
from pathlib import Path

DEPENDENCIES = ("pypdf", "python-docx", "lxml")
LICENSE_NAMES = ("license", "copying", "notice")


def collect(target: Path) -> dict[str, list[str]]:
    target.mkdir(parents=True, exist_ok=True)
    copied: dict[str, list[str]] = {}
    for package in DEPENDENCIES:
        distribution = metadata.distribution(package)
        available = distribution.files or []
        licenses = [
            item for item in available
            if item.parts
            and str(item.parts[0]).endswith(".dist-info")
            and item.name.casefold().startswith(LICENSE_NAMES)
            and distribution.locate_file(item).is_file()
        ]
        if not licenses:
            raise RuntimeError(f"No redistribution license text available for {package}")
        folder = target / f"{package}-{distribution.version}"
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for item in sorted(licenses, key=str):
            output = folder / item.name
            shutil.copy2(distribution.locate_file(item), output)
            paths.append(str(output.relative_to(target)).replace("\\", "/"))
        copied[package] = paths
    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.output)
    for package, paths in result.items():
        print(f"BUILDER_LICENSE {package}: {', '.join(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
