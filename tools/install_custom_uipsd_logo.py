#!/usr/bin/env python3
"""Install a hand-drawn title_bg_5.png at the exact game atlas dimensions."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import time

from PIL import Image


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Install a custom uipsd title logo")
    parser.add_argument("--project-root", type=pathlib.Path, required=True)
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--reference", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    input_path = args.input.resolve()
    reference_path = args.reference.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not reference_path.is_file():
        raise FileNotFoundError(reference_path)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = project_root / "backups" / f"manual_logo_before_resize_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_path = backup_dir / input_path.name
    shutil.copy2(input_path, backup_path)

    with Image.open(input_path) as source, Image.open(reference_path) as reference:
        source_rgba = source.convert("RGBA")
        target_size = reference.size
        resized = source_rgba.resize(target_size, Image.Resampling.LANCZOS)

    custom_dir = project_root / "localization" / "uipsd_custom_png"
    custom_dir.mkdir(parents=True, exist_ok=True)
    custom_path = custom_dir / input_path.name
    temporary = custom_path.with_suffix(".tmp.png")
    resized.save(temporary, format="PNG", optimize=True)
    temporary.replace(custom_path)
    shutil.copy2(custom_path, input_path)

    with Image.open(custom_path) as check:
        if check.size != target_size or check.mode != "RGBA":
            raise RuntimeError(
                f"Custom logo verification failed: size={check.size}, mode={check.mode}"
            )
        alpha_extrema = check.getchannel("A").getextrema()
        if alpha_extrema[0] != 0 or alpha_extrema[1] != 255:
            raise RuntimeError(f"Custom logo alpha verification failed: {alpha_extrema}")

    report = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input": str(input_path),
        "input_original_size": list(Image.open(backup_path).size),
        "reference": str(reference_path),
        "target_size": list(target_size),
        "backup": str(backup_path),
        "custom_override": str(custom_path),
        "installed_target": str(input_path),
        "sha256": sha256(custom_path),
    }
    (backup_dir / "install_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
