#!/usr/bin/env python3
"""Create a stable pre-localization uipsd PNG baseline for repeatable rendering."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare stable uipsd source PNGs")
    parser.add_argument("--project-root", type=pathlib.Path, required=True)
    parser.add_argument("--baseline-dir", type=pathlib.Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    source_root = project_root / "extracted" / "_tlg_png" / "uipsd"
    baseline_root = (args.baseline_dir or (project_root / "localization" / "uipsd_source_png")).resolve()
    existing = sorted(baseline_root.glob("*.png")) if baseline_root.is_dir() else []
    if existing:
        print(f"BASELINE_REUSED={baseline_root}")
        print(f"BASELINE_FILES={len(existing)}")
        return
    if not source_root.is_dir():
        raise FileNotFoundError(f"Extracted uipsd directory not found: {source_root}")

    baseline_root.mkdir(parents=True, exist_ok=False)
    copied = 0
    for source in sorted(source_root.glob("*.png")):
        shutil.copy2(source, baseline_root / source.name)
        copied += 1
    if copied == 0:
        raise ValueError(f"No PNG files found in: {source_root}")

    backup_overlay: pathlib.Path | None = None
    backup_root = project_root / "backups"
    backups = sorted(
        (
            path
            for path in backup_root.glob("uipsd_before_image_localization_*")
            if path.is_dir() and (path / "apply_manifest.json").is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if backups:
        backup_overlay = backups[0]
        payload = json.loads((backup_overlay / "apply_manifest.json").read_text(encoding="utf-8"))
        for entry in payload.get("entries", []):
            backup = pathlib.Path(entry["backup"])
            if backup.is_file():
                shutil.copy2(backup, baseline_root / backup.name)

    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_root": str(source_root),
        "backup_overlay": str(backup_overlay) if backup_overlay else None,
        "file_count": len(list(baseline_root.glob("*.png"))),
    }
    (baseline_root / "baseline_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"BASELINE_CREATED={baseline_root}")
    print(f"BASELINE_FILES={manifest['file_count']}")
    if backup_overlay:
        print(f"BASELINE_RESTORED_FROM={backup_overlay}")


if __name__ == "__main__":
    main()
