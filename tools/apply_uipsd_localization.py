#!/usr/bin/env python3
"""Safely apply rendered uipsd localization PNGs to the extracted tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import time

from PIL import Image


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply localized uipsd PNG files")
    parser.add_argument("--project-root", type=pathlib.Path)
    parser.add_argument("--source-dir", type=pathlib.Path)
    parser.add_argument("--target-dir", type=pathlib.Path)
    args = parser.parse_args()
    project_root = (args.project_root or pathlib.Path(__file__).resolve().parent.parent).resolve()
    source_root = (args.source_dir or (project_root / "build" / "uipsd_localize" / "candidate_png")).resolve()
    target_root = (args.target_dir or (project_root / "extracted" / "_tlg_png" / "uipsd")).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Candidate directory not found: {source_root}")
    if not target_root.is_dir():
        raise FileNotFoundError(f"Target directory not found: {target_root}")

    candidates = sorted(path for path in source_root.glob("*.png") if path.is_file())
    if not candidates:
        raise ValueError(f"No candidate PNG files found in: {source_root}")

    validated: list[tuple[pathlib.Path, pathlib.Path, str, str]] = []
    unchanged: list[str] = []
    for source in candidates:
        target = target_root / source.name
        if not target.is_file():
            raise FileNotFoundError(f"Original PNG not found: {target}")
        with Image.open(source) as candidate_image, Image.open(target) as target_image:
            candidate_properties = (candidate_image.size, candidate_image.mode)
            target_properties = (target_image.size, target_image.mode)
        if candidate_properties != target_properties:
            raise ValueError(
                f"Image geometry mismatch for {source.name}: "
                f"candidate={candidate_properties}, target={target_properties}"
            )
        original_hash = sha256(target)
        candidate_hash = sha256(source)
        if original_hash == candidate_hash:
            unchanged.append(source.name)
            continue
        validated.append((source, target, original_hash, candidate_hash))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_root = project_root / "backups" / f"uipsd_before_image_localization_{timestamp}"
    if validated:
        backup_root.mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, object]] = []
    for source, target, original_hash, candidate_hash in validated:
        backup = backup_root / target.name
        shutil.copy2(target, backup)
        if sha256(backup) != original_hash:
            raise IOError(f"Backup verification failed: {backup}")
        shutil.copy2(source, target)
        applied_hash = sha256(target)
        if applied_hash != candidate_hash:
            raise IOError(f"Applied file verification failed: {target}")
        entries.append(
            {
                "name": target.name,
                "source": str(source),
                "target": str(target),
                "backup": str(backup),
                "original_sha256": original_hash,
                "applied_sha256": applied_hash,
                "size": target.stat().st_size,
            }
        )

    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_root": str(source_root),
        "target_root": str(target_root),
        "backup_root": str(backup_root),
        "files_applied": len(entries),
        "files_unchanged": len(unchanged),
        "unchanged": unchanged,
        "entries": entries,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if validated:
        (backup_root / "apply_manifest.json").write_text(manifest_text, encoding="utf-8")
    report_path = project_root / "build" / "uipsd_localize" / "apply_manifest.json"
    report_path.write_text(manifest_text, encoding="utf-8")

    print(f"Applied {len(entries)} localized PNG files.")
    print(f"Unchanged: {len(unchanged)}")
    print(f"Backup: {backup_root if validated else 'not needed'}")
    print(f"Manifest: {report_path}")


if __name__ == "__main__":
    main()
