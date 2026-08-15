from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "extracted" / "_tlg_png" / "uipsd"
BUILD_DIR = ROOT / "build" / "uipsd_localize"
RECTS_PATH = BUILD_DIR / "pbd_state_rectangles.json"
OUTPUT_PATH = BUILD_DIR / "pbd_rectangle_ocr.json"
PAGE_DIR = BUILD_DIR / "pbd_ocr_pages"
RUNTIME_DIR = ROOT.parent / "translate_tool" / "paddleocr_runtime"
MODEL_HOME = ROOT.parent / "translate_tool"

os.environ["PADDLE_HOME"] = str(MODEL_HOME / "paddle_home")
os.environ["PADDLEX_HOME"] = str(MODEL_HOME / "paddlex_home")
os.environ["PADDLE_PDX_CACHE_HOME"] = str(MODEL_HOME / ".paddlex")
os.environ["USERPROFILE"] = str(MODEL_HOME)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
sys.path.insert(0, str(RUNTIME_DIR))

from paddleocr import PaddleOCR  # noqa: E402


CANDIDATE_STORAGES = {
    "dialog__pack",
    "file__pack",
    "file_voice__pack",
    "gesture_tips__pack",
    "popup_system__pack",
    "system1__pack",
    "system2__pack",
    "system3__pack",
    "system4__pack",
    "system5__pack",
    "system5_pulldown__pack",
    "system6__pack",
    "system6_pulldown__pack",
}

PAGE_SIZE = (2200, 2000)
TILE_SIZE = (540, 190)
CONTENT_MARGIN = 14


def normalize(text: str) -> str:
    return "".join(str(text).split()).strip()


def unique_rectangles(payload: dict) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for record in payload["records"]:
        for state in record["states"]:
            if state["storage"] not in CANDIDATE_STORAGES:
                continue
            key = (
                state["storage"],
                state["x"],
                state["y"],
                state["width"],
                state["height"],
                state["rotated"],
            )
            item = grouped.setdefault(
                key,
                {
                    "storage": state["storage"],
                    "x": state["x"],
                    "y": state["y"],
                    "width": state["width"],
                    "height": state["height"],
                    "rotated": state["rotated"],
                    "logical_width": state.get("logical_width"),
                    "logical_height": state.get("logical_height"),
                    "uses": [],
                },
            )
            item["uses"].append(
                {
                    "pbd_file": record["pbd_file"],
                    "key": record["key"],
                    "uiname": record["uiname"],
                    "name": record["name"],
                    "state": state["state"],
                }
            )
    result = []
    for item in grouped.values():
        visual_width = item["height"] if item["rotated"] else item["width"]
        visual_height = item["width"] if item["rotated"] else item["height"]
        if visual_width < 12 or visual_height < 8:
            continue
        if visual_width > 900 or visual_height > 190:
            continue
        if visual_width * visual_height > 130_000:
            continue
        result.append(item)
    return sorted(
        result,
        key=lambda row: (row["storage"], row["y"], row["x"], row["width"]),
    )


def logical_crop(item: dict, source: Image.Image) -> Image.Image:
    x, y = item["x"], item["y"]
    crop = source.crop((x, y, x + item["width"], y + item["height"]))
    if item["rotated"]:
        crop = crop.transpose(Image.Transpose.ROTATE_270)
    return crop.convert("RGBA")


def place_view(
    page: Image.Image,
    crop: Image.Image,
    view_box: tuple[int, int, int, int],
    background: str,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = view_box
    max_width, max_height = x2 - x1, y2 - y1
    scale = min(max_width / crop.width, max_height / crop.height, 4.0)
    size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    resized = crop.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, background)
    canvas.alpha_composite(resized)
    px = x1 + (max_width - size[0]) // 2
    py = y1 + (max_height - size[1]) // 2
    page.paste(canvas.convert("RGB"), (px, py))
    return (px, py, px + size[0], py + size[1])


def build_pages(rectangles: list[dict]) -> list[dict]:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    columns = PAGE_SIZE[0] // TILE_SIZE[0]
    rows = PAGE_SIZE[1] // TILE_SIZE[1]
    per_page = columns * rows
    pages: list[dict] = []
    sources: dict[str, Image.Image] = {}
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 13)

    for page_index, offset in enumerate(range(0, len(rectangles), per_page), start=1):
        page = Image.new("RGB", PAGE_SIZE, "#E6E8EC")
        draw = ImageDraw.Draw(page)
        placements: list[dict] = []
        for local_index, item in enumerate(rectangles[offset : offset + per_page]):
            column = local_index % columns
            row = local_index // columns
            tx = column * TILE_SIZE[0]
            ty = row * TILE_SIZE[1]
            draw.rectangle(
                (tx + 4, ty + 4, tx + TILE_SIZE[0] - 6, ty + TILE_SIZE[1] - 6),
                fill="#FFFFFF",
                outline="#AAB0BA",
                width=2,
            )
            source = sources.get(item["storage"])
            if source is None:
                source = Image.open(SOURCE_DIR / f"{item['storage']}.png").convert("RGBA")
                sources[item["storage"]] = source
            crop = logical_crop(item, source)
            view_y1 = ty + 28
            view_y2 = ty + TILE_SIZE[1] - CONTENT_MARGIN
            mid_x = tx + TILE_SIZE[0] // 2
            light_box = (tx + CONTENT_MARGIN, view_y1, mid_x - 7, view_y2)
            dark_box = (mid_x + 7, view_y1, tx + TILE_SIZE[0] - CONTENT_MARGIN, view_y2)
            light_actual = place_view(page, crop, light_box, "#F4F4F4")
            dark_actual = place_view(page, crop, dark_box, "#252A31")
            rect_id = offset + local_index + 1
            draw.text(
                (tx + 12, ty + 8),
                f"R{rect_id:04d} {item['storage']} {item['x']},{item['y']} {item['width']}x{item['height']}",
                fill="#343A46",
                font=font,
            )
            placements.append(
                {
                    "rect_id": f"R{rect_id:04d}",
                    "light_box": light_actual,
                    "dark_box": dark_actual,
                }
            )
        path = PAGE_DIR / f"page_{page_index:02d}.png"
        page.save(path)
        pages.append({"path": str(path), "placements": placements})
    return pages


def center_inside(box: list[int], region: list[int] | tuple[int, ...]) -> bool:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    rx1, ry1, rx2, ry2 = region
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


def parse_page_prediction(prediction: dict, placements: list[dict]) -> dict[str, dict]:
    buckets: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: {"light": [], "dark": []}
    )
    for text, score, box in zip(
        prediction.get("rec_texts", []),
        prediction.get("rec_scores", []),
        prediction.get("rec_boxes", []),
    ):
        normalized = normalize(str(text))
        if not normalized:
            continue
        numeric_box = [int(value) for value in box]
        for placement in placements:
            for view in ("light", "dark"):
                if center_inside(numeric_box, placement[f"{view}_box"]):
                    buckets[placement["rect_id"]][view].append(
                        {
                            "text": normalized,
                            "confidence": round(float(score), 4),
                            "box": numeric_box,
                        }
                    )
                    break
    return buckets


def main() -> None:
    global SOURCE_DIR, BUILD_DIR, RECTS_PATH, OUTPUT_PATH, PAGE_DIR
    parser = argparse.ArgumentParser(description="OCR text states from uipsd PBD rectangles")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--build-dir", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    SOURCE_DIR = args.source_dir.resolve()
    BUILD_DIR = args.build_dir.resolve()
    RECTS_PATH = BUILD_DIR / "pbd_state_rectangles.json"
    OUTPUT_PATH = BUILD_DIR / "pbd_rectangle_ocr.json"
    PAGE_DIR = BUILD_DIR / "pbd_ocr_pages"
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(f"uipsd source directory not found: {SOURCE_DIR}")
    payload = json.loads(RECTS_PATH.read_text(encoding="utf-8"))
    rectangles = unique_rectangles(payload)
    pages = build_pages(rectangles)
    print(f"rectangles={len(rectangles)} pages={len(pages)}", flush=True)

    ocr = PaddleOCR(
        lang="japan",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_rec_score_thresh=0.30,
    )
    by_id: dict[str, dict] = {}
    for page_index, page in enumerate(pages, start=1):
        prediction = ocr.predict(page["path"])[0]
        recognized = parse_page_prediction(prediction, page["placements"])
        by_id.update(recognized)
        print(f"ocr_page={page_index}/{len(pages)}", flush=True)

    output_rows = []
    for index, item in enumerate(rectangles, start=1):
        rect_id = f"R{index:04d}"
        views = by_id.get(rect_id, {"light": [], "dark": []})
        output_rows.append({"rect_id": rect_id, **item, "ocr": views})

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "rectangle_count": len(output_rows),
                "page_count": len(pages),
                "rows": output_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    recognized_count = sum(
        1 for row in output_rows if row["ocr"]["light"] or row["ocr"]["dark"]
    )
    print(f"recognized_rectangles={recognized_count}")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
