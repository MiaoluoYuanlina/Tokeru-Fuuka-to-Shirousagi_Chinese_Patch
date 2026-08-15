from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "extracted" / "_tlg_png" / "uipsd"
OUTPUT_DIR = ROOT / "build" / "uipsd_scan"
RUNTIME_DIR = ROOT.parent / "translate_tool" / "paddleocr_runtime"
MODEL_HOME = ROOT.parent / "translate_tool"

os.environ["PADDLE_HOME"] = str(MODEL_HOME / "paddle_home")
os.environ["PADDLEX_HOME"] = str(MODEL_HOME / "paddlex_home")
os.environ["PADDLE_PDX_CACHE_HOME"] = str(MODEL_HOME / ".paddlex")
os.environ["USERPROFILE"] = str(MODEL_HOME)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
sys.path.insert(0, str(RUNTIME_DIR))

from paddleocr import PaddleOCR  # noqa: E402


CANDIDATES = [
    "dialog__pack.png",
    "file__pack.png",
    "file_voice__pack.png",
    "gesture_tips__pack.png",
    "popup_quick__bg0.png",
    "popup_system__bg0.png",
    "popup_system__pack.png",
    "popup_volume__bg0.png",
    "system1__pack.png",
    "system2__pack.png",
    "system3__pack.png",
    "system4__pack.png",
    "system5__pack.png",
    "system5_pulldown__pack.png",
    "system6__pack.png",
    "system6_pulldown__pack.png",
    "title_bg_2.png",
    "title_bg_5.png",
    "title_bg_6.png",
]


def composite_pair(source: Image.Image) -> tuple[Image.Image, int, int, float]:
    rgba = source.convert("RGBA")
    width, height = rgba.size
    scale = 1.5 if max(width, height) <= 900 else 1.0
    if scale != 1.0:
        rgba = rgba.resize(
            (round(width * scale), round(height * scale)), Image.Resampling.LANCZOS
        )
    scaled_width, scaled_height = rgba.size
    gap = 24
    canvas = Image.new("RGB", (scaled_width * 2 + gap, scaled_height), "#F4F4F4")
    light = Image.new("RGBA", rgba.size, "#F4F4F4")
    dark = Image.new("RGBA", rgba.size, "#252A31")
    light.alpha_composite(rgba)
    dark.alpha_composite(rgba)
    canvas.paste(light.convert("RGB"), (0, 0))
    canvas.paste(dark.convert("RGB"), (scaled_width + gap, 0))
    return canvas, scaled_width, gap, scale


def normalize_text(text: str) -> str:
    return "".join(text.split()).strip()


def overlaps(a: dict, b: dict) -> bool:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = ix * iy
    smaller = min(a["width"] * a["height"], b["width"] * b["height"])
    return smaller > 0 and intersection / smaller >= 0.55


def palette_for_box(image: Image.Image, box: dict) -> list[str]:
    rgba = image.convert("RGBA")
    x1 = max(0, box["x"])
    y1 = max(0, box["y"])
    x2 = min(rgba.width, x1 + max(1, box["width"]))
    y2 = min(rgba.height, y1 + max(1, box["height"]))
    crop = rgba.crop((x1, y1, x2, y2))
    colors: Counter[tuple[int, int, int]] = Counter()
    for red, green, blue, alpha in crop.getdata():
        if alpha < 48:
            continue
        if red > 185 and blue > 125 and green < 105:
            continue
        colors[(red // 16 * 16, green // 16 * 16, blue // 16 * 16)] += 1
    return [f"#{r:02X}{g:02X}{b:02X}" for (r, g, b), _ in colors.most_common(4)]


def parse_result(result: dict, original: Image.Image, scaled_width: int, gap: int, scale: float) -> list[dict]:
    rows: list[dict] = []
    texts = result.get("rec_texts", [])
    scores = result.get("rec_scores", [])
    boxes = result.get("rec_boxes", [])
    angles = result.get("textline_orientation_angles", [])
    for index, text in enumerate(texts):
        normalized = normalize_text(str(text))
        if not normalized:
            continue
        x1, y1, x2, y2 = [int(value) for value in boxes[index]]
        source_view = "light"
        if x1 >= scaled_width + gap:
            x1 -= scaled_width + gap
            x2 -= scaled_width + gap
            source_view = "dark"
        elif x2 > scaled_width:
            continue
        box = {
            "x": max(0, round(x1 / scale)),
            "y": max(0, round(y1 / scale)),
            "width": max(1, round((x2 - x1) / scale)),
            "height": max(1, round((y2 - y1) / scale)),
        }
        row = {
            **box,
            "text": normalized,
            "confidence": round(float(scores[index]), 4),
            "orientation": "vertical" if box["height"] > box["width"] * 1.8 else "horizontal",
            "angle": int(angles[index]) if index < len(angles) else -1,
            "source_view": source_view,
            "font_size_estimate_px": max(1, round(box["height"] * 0.82)),
        }
        row["palette"] = palette_for_box(original, row)
        rows.append(row)

    deduplicated: list[dict] = []
    for candidate in sorted(rows, key=lambda item: item["confidence"], reverse=True):
        duplicate = next(
            (
                existing
                for existing in deduplicated
                if normalize_text(existing["text"]) == normalize_text(candidate["text"])
                and overlaps(existing, candidate)
            ),
            None,
        )
        if duplicate is None:
            deduplicated.append(candidate)
    return sorted(deduplicated, key=lambda item: (item["y"], item["x"]))


def main(argv: list[str] | None = None) -> None:
    global SOURCE_DIR, OUTPUT_DIR
    parser = argparse.ArgumentParser(description="Scan uipsd PNG text with local OCR")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.source_dir:
        SOURCE_DIR = args.source_dir.resolve()
    if args.output_dir:
        OUTPUT_DIR = args.output_dir.resolve()
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(f"uipsd PNG directory not found: {SOURCE_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prepared_dir = OUTPUT_DIR / "ocr_inputs"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    ocr = PaddleOCR(
        lang="japan",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_rec_score_thresh=0.35,
    )
    all_results: list[dict] = []
    for index, file_name in enumerate(CANDIDATES, start=1):
        source_path = SOURCE_DIR / file_name
        original = Image.open(source_path)
        prepared, scaled_width, gap, scale = composite_pair(original)
        prepared_path = prepared_dir / file_name
        prepared.save(prepared_path)
        prediction = ocr.predict(str(prepared_path))
        detections = parse_result(
            prediction[0], original, scaled_width=scaled_width, gap=gap, scale=scale
        )
        all_results.append(
            {
                "file_name": file_name,
                "width": original.width,
                "height": original.height,
                "scale": scale,
                "detections": detections,
            }
        )
        print(f"[{index:02d}/{len(CANDIDATES):02d}] {file_name}: {len(detections)}")

    output_path = OUTPUT_DIR / "ocr_results.json"
    output_path.write_text(
        json.dumps(
            {
                "source_directory": str(SOURCE_DIR),
                "candidate_count": len(CANDIDATES),
                "results": all_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"OCR_RESULTS={output_path}")


if __name__ == "__main__":
    main()
