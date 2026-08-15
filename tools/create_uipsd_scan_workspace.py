#!/usr/bin/env python3
"""Create contact sheets and a machine-readable manifest for uipsd PNG review."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        pathlib.Path(r"C:\Windows\Fonts\arial.ttf"),
        pathlib.Path(r"C:\Windows\Fonts\msyh.ttc"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def checkerboard(width: int, height: int, block: int = 16) -> Image.Image:
    result = Image.new("RGBA", (width, height), "#D9D9D9")
    draw = ImageDraw.Draw(result)
    for y in range(0, height, block):
        for x in range(0, width, block):
            if ((x // block) + (y // block)) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill="#F2F2F2")
    return result


def thumbnail_panel(path: pathlib.Path, max_width: int, max_height: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    ratio = min(max_width / image.width, max_height / image.height, 1.0)
    if ratio < 1.0:
        image = image.resize(
            (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    panel = checkerboard(max_width, max_height)
    left = (max_width - image.width) // 2
    top = (max_height - image.height) // 2
    panel.alpha_composite(image, (left, top))
    return panel


def build_sheets(
    paths: list[pathlib.Path],
    output_dir: pathlib.Path,
    prefix: str,
    columns: int,
    rows: int,
    image_width: int,
    image_height: int,
) -> list[str]:
    label_height = 46
    gutter = 20
    page_size = columns * rows
    outputs: list[str] = []
    label_font = font(24)
    for page_index in range(0, len(paths), page_size):
        subset = paths[page_index : page_index + page_size]
        canvas_width = columns * (image_width + gutter) + gutter
        canvas_height = rows * (image_height + label_height + gutter) + gutter
        canvas = Image.new("RGB", (canvas_width, canvas_height), "#20242A")
        draw = ImageDraw.Draw(canvas)
        for slot, path in enumerate(subset):
            column = slot % columns
            row = slot // columns
            left = gutter + column * (image_width + gutter)
            top = gutter + row * (image_height + label_height + gutter)
            panel = thumbnail_panel(path, image_width, image_height).convert("RGB")
            canvas.paste(panel, (left, top))
            label = path.name
            draw.rectangle(
                (left, top + image_height, left + image_width, top + image_height + label_height),
                fill="#111827",
            )
            draw.text(
                (left + 10, top + image_height + 8),
                label,
                font=label_font,
                fill="#FFFFFF",
            )
        output_path = output_dir / f"{prefix}_{page_index // page_size + 1:02d}.png"
        canvas.save(output_path, optimize=True)
        outputs.append(str(output_path))
    return outputs


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(
            "Usage: create_uipsd_scan_workspace.py <project-root> <output-dir> [source-dir]"
        )
    project_root = pathlib.Path(sys.argv[1]).resolve()
    output_dir = pathlib.Path(sys.argv[2]).resolve()
    source_dir = (
        pathlib.Path(sys.argv[3]).resolve()
        if len(sys.argv) == 4
        else project_root / "extracted" / "_tlg_png" / "uipsd"
    )
    if not source_dir.is_dir():
        raise FileNotFoundError(f"uipsd PNG directory not found: {source_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(source_dir.glob("*.png"), key=lambda item: item.name.casefold())
    manifest: list[dict[str, object]] = []
    for path in paths:
        with Image.open(path) as image:
            alpha = image.convert("RGBA").getchannel("A")
            alpha_extrema = alpha.getextrema()
            manifest.append(
                {
                    "file_name": path.name,
                    "absolute_path": str(path),
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "has_transparency": alpha_extrema[0] < 255,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "category": "pack" if "__pack" in path.stem else "background",
                }
            )

    pack_paths = [path for path in paths if "__pack" in path.stem]
    background_paths = [path for path in paths if path not in pack_paths]
    contact_sheets = build_sheets(
        pack_paths, output_dir, "pack", 2, 4, 900, 600
    ) + build_sheets(
        background_paths, output_dir, "background", 1, 2, 1400, 800
    )
    report = {
        "source_directory": str(source_dir),
        "files_total": len(paths),
        "pack_files": len(pack_paths),
        "background_files": len(background_paths),
        "contact_sheets": contact_sheets,
        "files": manifest,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("files_total", "pack_files", "background_files")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
