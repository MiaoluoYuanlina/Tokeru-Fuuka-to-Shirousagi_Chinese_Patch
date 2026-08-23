#!/usr/bin/env python3
"""Render translated 406x66 speaker-name PNGs from the OCR workbook export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS_SIZE = (406, 66)
TEXT_FILL = (19, 20, 23, 255)
INNER_STROKE = (208, 222, 240, 255)
OUTER_STROKE = (230, 223, 243, 255)
MAX_TEXT_BOX = (392, 64)


def load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(font_path), size)
    try:
        variation_names = font.get_variation_names()
        if b"Black" in variation_names:
            font.set_variation_by_name(b"Black")
        elif b"Bold" in variation_names:
            font.set_variation_by_name(b"Bold")
    except (AttributeError, OSError):
        pass
    return font


def fit_font(text: str, font_path: Path, preferred_size: int = 54) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    probe = Image.new("L", CANVAS_SIZE, 0)
    draw = ImageDraw.Draw(probe)
    for size in range(preferred_size, 19, -1):
        font = load_font(font_path, size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=5)
        if box[2] - box[0] <= MAX_TEXT_BOX[0] and box[3] - box[1] <= MAX_TEXT_BOX[1]:
            return font, box
    raise RuntimeError(f"translation cannot fit: {text!r}")


def render_name(text: str, font_path: Path) -> tuple[Image.Image, dict]:
    font, box = fit_font(text, font_path)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = (CANVAS_SIZE[0] - width) // 2 - box[0]
    y = (CANVAS_SIZE[1] - height) // 2 - box[1]

    image = Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    # Outer lavender fringe, then the cooler inner outline and dark glyph core.
    draw.text(
        (x, y),
        text,
        font=font,
        fill=INNER_STROKE,
        stroke_width=5,
        stroke_fill=OUTER_STROKE,
    )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=TEXT_FILL,
        stroke_width=2,
        stroke_fill=INNER_STROKE,
    )
    alpha_box = image.getchannel("A").getbbox()
    if alpha_box is None:
        raise RuntimeError(f"render produced no visible pixels: {text!r}")
    if alpha_box[0] < 0 or alpha_box[1] < 0 or alpha_box[2] > CANVAS_SIZE[0] or alpha_box[3] > CANVAS_SIZE[1]:
        raise RuntimeError(f"render overflow: {text!r} bbox={alpha_box}")
    return image, {
        "font_size": font.size,
        "text_bbox": list(alpha_box),
        "text_width": alpha_box[2] - alpha_box[0],
        "text_height": alpha_box[3] - alpha_box[1],
    }


def make_contact_sheet(entries: list[dict], source_dir: Path, rendered_dir: Path, output_path: Path) -> None:
    columns = 4
    rows = (len(entries) + columns - 1) // columns
    cell_width = 420
    cell_height = 154
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#F4F6F8")
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 15)
    small_font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 12)
    for index, entry in enumerate(entries):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * cell_height
        draw.rectangle((left, top, left + cell_width - 1, top + cell_height - 1), outline="#C8D0D8")
        draw.text((left + 8, top + 5), entry["file_name"], font=small_font, fill="#334155")
        draw.text(
            (left + 190, top + 5),
            f'{entry["original_text"]} → {entry["translation_zh_cn"]}',
            font=small_font,
            fill="#475569",
        )
        for image_index, image_path in enumerate((source_dir / entry["file_name"], rendered_dir / entry["file_name"])):
            image = Image.open(image_path).convert("RGBA")
            background = Image.new("RGBA", image.size, "#FFFFFF")
            background.alpha_composite(image)
            y = top + 29 + image_index * 59
            sheet.paste(background.convert("RGB"), (left + 7, y))
            draw.text((left + 365, y + 21), "原" if image_index == 0 else "中", font=label_font, fill="#1E3A5F")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations", type=Path)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("font", type=Path)
    args = parser.parse_args()

    document = json.loads(args.translations.read_text(encoding="utf-8"))
    entries = document.get("translations", [])
    if not entries:
        raise RuntimeError("no translated rows were found")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []
    for entry in entries:
        source = args.source_dir / entry["file_name"]
        if not source.is_file():
            raise FileNotFoundError(source)
        source_image = Image.open(source).convert("RGBA")
        if source_image.size != CANVAS_SIZE:
            raise RuntimeError(f"unexpected source dimensions: {source} {source_image.size}")
        rendered, metrics = render_name(entry["translation_zh_cn"], args.font)
        destination = args.output_dir / entry["file_name"]
        rendered.save(destination, format="PNG", optimize=True)
        manifest_entries.append(
            {
                "file_name": entry["file_name"],
                "original_text": entry["original_text"],
                "translation_zh_cn": entry["translation_zh_cn"],
                "source_dimensions": list(source_image.size),
                "output_dimensions": list(rendered.size),
                **metrics,
            }
        )

    contact_sheet = args.output_dir.parent / "name_render_comparison.png"
    make_contact_sheet(entries, args.source_dir, args.output_dir, contact_sheet)
    manifest = {
        "font": str(args.font.resolve()),
        "source_dir": str(args.source_dir.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "rendered_count": len(manifest_entries),
        "canvas_size": list(CANVAS_SIZE),
        "entries": manifest_entries,
        "contact_sheet": str(contact_sheet.resolve()),
    }
    manifest_path = args.output_dir.parent / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "rendered_count": len(manifest_entries),
        "minimum_font_size": min(item["font_size"] for item in manifest_entries),
        "maximum_text_width": max(item["text_width"] for item in manifest_entries),
        "contact_sheet": str(contact_sheet),
        "manifest": str(manifest_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
