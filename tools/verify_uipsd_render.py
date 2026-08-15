#!/usr/bin/env python3
"""Verify candidate image geometry and that every rendered text box fits its area."""

from __future__ import annotations

import argparse
import json
import pathlib

from PIL import Image


def inside(box: list[int], area: list[int]) -> bool:
    return box[0] >= area[0] and box[1] >= area[1] and box[2] <= area[2] and box[3] <= area[3]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify rendered uipsd PNG files")
    parser.add_argument("--source-dir", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-dir", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    candidate_dir = args.candidate_dir.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dimension_errors: list[dict[str, object]] = []
    for name in manifest.get("files", []):
        source_path = source_dir / name
        candidate_path = candidate_dir / name
        if not source_path.is_file() or not candidate_path.is_file():
            dimension_errors.append({"file": name, "error": "missing source or candidate"})
            continue
        with Image.open(source_path) as source, Image.open(candidate_path) as candidate:
            if source.size != candidate.size or source.mode != candidate.mode:
                dimension_errors.append(
                    {
                        "file": name,
                        "source": {"size": source.size, "mode": source.mode},
                        "candidate": {"size": candidate.size, "mode": candidate.mode},
                    }
                )

    overflow: list[dict[str, object]] = []
    scaling_count = 0
    minimum_font_size: int | None = None
    checked_text_boxes = 0
    for edit in manifest.get("edits", []):
        render = edit.get("render")
        if not render:
            continue
        checked_text_boxes += 1
        font_size = render.get("font_size")
        if isinstance(font_size, int):
            minimum_font_size = font_size if minimum_font_size is None else min(minimum_font_size, font_size)
        if render.get("fitted_by_scaling"):
            scaling_count += 1
        box = render.get("box")
        area = render.get("available_box")
        if not box or not area or not inside(box, area):
            overflow.append(
                {
                    "file": edit.get("file_name"),
                    "text": edit.get("chinese_translation"),
                    "box": box,
                    "available_box": area,
                }
            )

    report = {
        "candidate_files": len(manifest.get("files", [])),
        "checked_text_boxes": checked_text_boxes,
        "dimension_error_count": len(dimension_errors),
        "overflow_count": len(overflow),
        "fitted_by_scaling_count": scaling_count,
        "minimum_font_size": minimum_font_size,
        "dimension_errors": dimension_errors,
        "overflow": overflow,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("candidate_files", "checked_text_boxes", "dimension_error_count", "overflow_count", "fitted_by_scaling_count", "minimum_font_size")}, ensure_ascii=False))
    print(f"REPORT={args.report.resolve()}")
    if dimension_errors or overflow:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
