from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "extracted" / "_tlg_png" / "uipsd"
BUILD_DIR = ROOT / "build" / "uipsd_localize"
OUTPUT_DIR = BUILD_DIR / "candidate_png"
OCR_PATH = BUILD_DIR / "pbd_rectangle_ocr.json"
MATCH_PATH = BUILD_DIR / "pbd_translation_matches.json"
MANIFEST_PATH = BUILD_DIR / "render_manifest.json"
TRANSLATION_PATH = BUILD_DIR / "translations_from_excel.json"
CUSTOM_DIR = ROOT / "localization" / "uipsd_custom_png"

SANS = Path(r"C:\Windows\Fonts\msyhbd.ttc")
SERIF = Path(r"C:\Windows\Fonts\simsun.ttc")
DECORATIVE = Path(r"C:\Windows\Fonts\STLITI.TTF")
FALLBACK_DECORATIVE = Path(r"C:\Windows\Fonts\STXINGKA.TTF")

PAGE_SIZE = (2200, 2000)
TILE_SIZE = (540, 190)
CONTENT_MARGIN = 14
PAGE_COLUMNS = PAGE_SIZE[0] // TILE_SIZE[0]
PAGE_ROWS = PAGE_SIZE[1] // TILE_SIZE[1]
PER_PAGE = PAGE_COLUMNS * PAGE_ROWS

# These crops are icons, incomplete words, or catalog-neighbor false positives.
DENY_RECT_IDS = {
    "R0082", "R0083", "R0109", "R0113", "R0114", "R0116",
    "R0139", "R0143", "R0144", "R0149", "R0152",
    "R0174", "R0178", "R0179", "R0182", "R0184", "R0188",
    "R0317", "R0330", "R0331", "R0333", "R0340",
    "R0359", "R0396", "R0397", "R0398", "R0399",
    "R0452", "R0474",
}

MANUAL_RECT_TRANSLATIONS = {
    # Two lines share R0005.
    "R0005": None,
    # Gesture help/action labels, including catalog omissions.
    "R0170": ("ドラマチックモード ON/OFF", "剧情模式 开/关"),
    "R0171": ("スクリーンショット保存", "保存截图"),
    "R0172": ("バックログ", "回溯记录"),
    "R0173": ("メッセージスキップ", "跳过文本"),
    "R0174": ("クイックロード", "快速读取"),
    "R0175": ("オートプレイ", "自动播放"),
    "R0176": ("ボイス再生", "播放语音"),
    "R0177": ("前の選択肢へ戻る", "返回上一个选项"),
    "R0180": ("お気に入りボイス", "收藏语音"),
    "R0181": ("シナリオチャート", "剧情图表"),
    "R0183": ("システム", "系统"),
    "R0184": ("セーブ", "保存"),
    "R0185": ("ロード", "读取"),
    "R0186": ("ウィンドウ消去", "隐藏窗口"),
    "R0187": ("ゲームの最小化", "最小化游戏"),
    "R0189": ("無効", "无效"),
    "R0190": ("タイトルに戻る", "返回标题画面"),
    "R0192": ("クイックセーブ", "快速保存"),
    # System page labels missed by the curated catalog/OCR merge.
    "R0208": ("システム設定画面を表示", "显示系统设置画面"),
    "R0227": ("右ボタンクリック", "右键单击"),
    "R0232": ("マウスオーバー", "鼠标悬停"),
    "R0234": ("マウスオーバー", "鼠标悬停"),
    "R0237": ("マウスオーバー", "鼠标悬停"),
    "R0326": ("秋穂", "秋穗"),
    "R0358": ("初期状態に戻す", "恢复初始状态"),
    "R0359": ("ロード", "读取"),
    # Gesture page secondary/vertical actions.
    "R0376": ("右クリックジェスチャー", "右键手势"),
    "R0378": ("ジェスチャー機能", "手势功能"),
    "R0379": ("タイトルに戻る", "返回标题画面"),
    "R0380": ("ウィンドウ消去", "隐藏窗口"),
    "R0381": ("クイックセーブ", "快速保存"),
    "R0382": ("クイックロード", "快速读取"),
    "R0383": ("OFF", "关闭"),
    "R0384": ("OFF", "关闭"),
    "R0385": ("オートプレイ", "自动播放"),
    "R0396": ("システム", "系统"),
    "R0397": ("セーブ", "保存"),
    "R0398": ("ロード", "读取"),
    "R0399": ("無効", "禁用"),
    # Missing normal/hover menu states.
    "R0416": ("ドラマチックモード ON/OFF", "剧情模式 开/关"),
    "R0421": ("ロード", "读取"),
    "R0423": ("ロード", "读取"),
    # Shortcut help labels and vertical fixed actions.
    "R0452": ("ショートカット設定", "快捷键设置"),
    "R0454": ("クイックロード", "快速读取"),
    "R0456": ("前の選択肢へ戻る", "返回上一个选项"),
    "R0457": ("ウィンドウの消去", "隐藏窗口"),
    "R0458": ("お気に入りボイス", "收藏语音"),
    "R0459": ("シナリオチャート", "剧情图表"),
    "R0460": ("ゲームの最小化", "最小化游戏"),
    "R0461": ("タイトルに戻る", "返回标题画面"),
    "R0462": ("クイックセーブ", "快速保存"),
    "R0471": ("カーソル移動", "移动光标"),
    "R0472": ("オートプレイ", "自动播放"),
    "R0473": ("ボイス再生", "播放语音"),
    "R0474": ("バックログ", "回溯记录"),
    "R0475": ("ゲーム終了", "退出游戏"),
    "R0476": ("システム", "系统"),
    "R0482": ("ロード", "读取"),
    "R0484": ("セーブ", "保存"),
}

TRANSLATIONS_BY_TEXT: dict[str, str] = {}


def compact(text: str) -> str:
    return re.sub(r"[\s・･／/()（）「」『』\[\].,。!?！？:*＊©×△▽▼→←ー—_\-]", "", str(text)).lower()


def similarity(left: str, right: str) -> float:
    a, b = compact(left), compact(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.65 + min(len(a), len(b)) / max(len(a), len(b)) * 0.35
    return SequenceMatcher(None, a, b).ratio()


def load_translation_lookup() -> None:
    TRANSLATIONS_BY_TEXT.clear()
    if not TRANSLATION_PATH.is_file():
        return
    payload = json.loads(TRANSLATION_PATH.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        original = str(row.get("original_text", "")).strip()
        translation = str(row.get("chinese_translation", "")).strip()
        if original and translation:
            TRANSLATIONS_BY_TEXT[compact(original)] = translation


def translated_text(original: str, fallback: str) -> str:
    result = TRANSLATIONS_BY_TEXT.get(compact(original), fallback)
    punctuation_fixes = {
        "如果不需要此功能，请选择“OFF。": "如果不需要此功能，请选择“OFF”。",
    }
    return punctuation_fixes.get(result, result)


def union_boxes(items: list[dict]) -> tuple[int, int, int, int]:
    return (
        min(item["box"][0] for item in items),
        min(item["box"][1] for item in items),
        max(item["box"][2] for item in items),
        max(item["box"][3] for item in items),
    )


def best_ocr_group(row: dict, original_text: str) -> tuple[str, list[dict]] | None:
    ranked: list[tuple[float, str, list[dict]]] = []
    for view in ("light", "dark"):
        items = sorted(row["ocr"].get(view, []), key=lambda item: (item["box"][1], item["box"][0]))
        for item in items:
            ranked.append((similarity(original_text, item["text"]), view, [item]))
        if len(items) > 1:
            joined = "".join(item["text"] for item in items)
            ranked.append((similarity(original_text, joined), view, items))
    if not ranked:
        return None
    _, view, items = max(ranked, key=lambda value: value[0])
    return view, items


def actual_view_box(rect_id: str, crop_width: int, crop_height: int, view: str) -> tuple[tuple[int, int, int, int], float]:
    index = int(rect_id[1:]) - 1
    local_index = index % PER_PAGE
    column = local_index % PAGE_COLUMNS
    row = local_index // PAGE_COLUMNS
    tx = column * TILE_SIZE[0]
    ty = row * TILE_SIZE[1]
    view_y1 = ty + 28
    view_y2 = ty + TILE_SIZE[1] - CONTENT_MARGIN
    mid_x = tx + TILE_SIZE[0] // 2
    if view == "light":
        box = (tx + CONTENT_MARGIN, view_y1, mid_x - 7, view_y2)
    else:
        box = (mid_x + 7, view_y1, tx + TILE_SIZE[0] - CONTENT_MARGIN, view_y2)
    max_width, max_height = box[2] - box[0], box[3] - box[1]
    scale = min(max_width / crop_width, max_height / crop_height, 4.0)
    resized_width = max(1, round(crop_width * scale))
    resized_height = max(1, round(crop_height * scale))
    px = box[0] + (max_width - resized_width) // 2
    py = box[1] + (max_height - resized_height) // 2
    return (px, py, px + resized_width, py + resized_height), scale


def source_bbox(rect_id: str, row: dict, view: str, items: list[dict]) -> tuple[int, int, int, int]:
    crop_width = row["height"] if row["rotated"] else row["width"]
    crop_height = row["width"] if row["rotated"] else row["height"]
    actual, scale = actual_view_box(rect_id, crop_width, crop_height, view)
    x1, y1, x2, y2 = union_boxes(items)
    result = (
        math.floor((x1 - actual[0]) / scale),
        math.floor((y1 - actual[1]) / scale),
        math.ceil((x2 - actual[0]) / scale),
        math.ceil((y2 - actual[1]) / scale),
    )
    return (
        max(0, min(crop_width - 1, result[0])),
        max(0, min(crop_height - 1, result[1])),
        max(1, min(crop_width, result[2])),
        max(1, min(crop_height, result[3])),
    )


def logical_crop(image: Image.Image, row: dict) -> Image.Image:
    x, y = row["x"], row["y"]
    crop = image.crop((x, y, x + row["width"], y + row["height"])).convert("RGBA")
    if row["rotated"]:
        crop = crop.transpose(Image.Transpose.ROTATE_270)
    return crop


def paste_logical_crop(image: Image.Image, row: dict, crop: Image.Image) -> None:
    if row["rotated"]:
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    # Replace the complete atlas rectangle. Alpha-compositing would keep the
    # Japanese glyphs wherever the newly erased crop is transparent.
    image.paste(crop, (row["x"], row["y"]))


def expand_box(box: tuple[int, int, int, int], size: tuple[int, int], padding: int = 2) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (
        max(0, x1 - padding),
        max(0, y1 - padding),
        min(size[0], x2 + padding),
        min(size[1], y2 + padding),
    )


def average_rgba(pixels: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    if not pixels:
        return (0, 0, 0, 0)
    return tuple(round(sum(pixel[index] for pixel in pixels) / len(pixels)) for index in range(4))


def pick_text_color(crop: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    pixels = list(crop.crop(box).getdata())
    visible = [pixel for pixel in pixels if pixel[3] >= 96 and not (pixel[0] > 180 and pixel[2] > 130 and pixel[1] < 110)]
    if not visible:
        return (48, 56, 86, 255)
    alpha_zero_ratio = sum(pixel[3] < 32 for pixel in pixels) / max(1, len(pixels))
    quantized = Counter((p[0] // 16 * 16, p[1] // 16 * 16, p[2] // 16 * 16) for p in visible)
    if alpha_zero_ratio > 0.08:
        color = quantized.most_common(1)[0][0]
        return (*color, 255)

    border = []
    if y1 > 0:
        border.extend(crop.crop((x1, y1 - 1, x2, y1)).getdata())
    if y2 < crop.height:
        border.extend(crop.crop((x1, y2, x2, y2 + 1)).getdata())
    background = average_rgba([p for p in border if p[3] > 64])
    ranked = sorted(
        quantized.items(),
        key=lambda item: (
            (item[0][0] - background[0]) ** 2 + (item[0][1] - background[1]) ** 2 + (item[0][2] - background[2]) ** 2,
            item[1],
        ),
        reverse=True,
    )
    color = ranked[0][0]
    return (*color, 255)


def erase_text(crop: Image.Image, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = expand_box(box, crop.size, padding=max(1, round((box[3] - box[1]) * 0.12)))
    region = crop.crop((x1, y1, x2, y2))
    pixels = list(region.getdata())
    transparent_ratio = sum(pixel[3] < 32 for pixel in pixels) / max(1, len(pixels))
    if transparent_ratio > 0.05:
        clear = Image.new("RGBA", region.size, (0, 0, 0, 0))
        crop.paste(clear, (x1, y1))
        return

    source = crop.load()
    target = crop.load()
    top_y = max(0, y1 - 2)
    bottom_y = min(crop.height - 1, y2 + 1)
    span = max(1, y2 - y1)
    for y in range(y1, y2):
        factor = (y - y1 + 0.5) / span
        for x in range(x1, x2):
            top = source[x, top_y]
            bottom = source[x, bottom_y]
            target[x, y] = tuple(round(top[i] * (1 - factor) + bottom[i] * factor) for i in range(4))


def best_wrap(text: str, lines: int) -> str:
    normalized = "".join(text.splitlines())
    if lines <= 1 or len(normalized) <= 3:
        return normalized
    lines = max(1, min(lines, len(normalized)))
    base, remainder = divmod(len(normalized), lines)
    chunks: list[str] = []
    start = 0
    for index in range(lines):
        length = base + (1 if index < remainder else 0)
        chunks.append(normalized[start : start + length])
        start += length
    return "\n".join(chunks)


def make_text_layer(
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int, int],
    spacing: int,
    align: str,
) -> Image.Image:
    measure = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(measure)
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
    width = max(1, math.ceil(box[2] - box[0]))
    height = max(1, math.ceil(box[3] - box[1]))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(layer).multiline_text(
        (-box[0], -box[1]),
        text,
        font=font,
        fill=color,
        spacing=spacing,
        align=align,
    )
    return layer


def draw_translation(
    crop: Image.Image,
    original_box: tuple[int, int, int, int],
    text: str,
    color: tuple[int, int, int, int],
    font_path: Path = SANS,
    source_line_count: int = 1,
    forced_center: bool | None = None,
) -> dict:
    x1, y1, x2, y2 = original_box
    original_width = max(1, x2 - x1)
    original_height = max(1, y2 - y1)
    original_center = (x1 + x2) / 2
    centered = abs(original_center - crop.width / 2) <= max(8, crop.width * 0.10)
    if forced_center is not None:
        centered = forced_center
    area_left = 3 if centered else max(2, min(crop.width - 3, x1 - 1))
    area_right = max(area_left + 1, crop.width - 3)
    area_top = 2
    area_bottom = max(area_top + 1, crop.height - 2)
    max_width = max(1, area_right - area_left)
    max_height = max(1, area_bottom - area_top)
    source_lines = max(1, source_line_count)
    per_line_height = max(1, round(original_height / source_lines))
    start_size = max(9, min(96, round(per_line_height * 0.92)))
    max_lines_by_height = max(1, min(3, max_height // 9))
    preferred_lines = 2 if source_lines > 1 else 1
    candidate_line_counts = list(range(preferred_lines, max_lines_by_height + 1))
    candidate_line_counts += list(range(1, preferred_lines))
    candidate_line_counts = list(dict.fromkeys(candidate_line_counts))
    align = "center" if centered else "left"

    chosen: tuple[int, int, str, Image.Image] | None = None
    for line_count in candidate_line_counts:
        rendered = best_wrap(text, line_count)
        for size in range(start_size, 5, -1):
            font = ImageFont.truetype(str(font_path), size)
            spacing = max(0, round(size * 0.08))
            layer = make_text_layer(rendered, font, color, spacing, align)
            if layer.width <= max_width and layer.height <= max_height:
                score = (size, -line_count)
                if chosen is None or score > (chosen[0], chosen[1]):
                    chosen = (size, -line_count, rendered, layer)
                break

    fitted_by_scaling = False
    if chosen is None:
        line_count = max(candidate_line_counts)
        rendered = best_wrap(text, line_count)
        font = ImageFont.truetype(str(font_path), 6)
        layer = make_text_layer(rendered, font, color, 0, align)
        scale = min(max_width / layer.width, max_height / layer.height, 1.0)
        layer = layer.resize(
            (max(1, round(layer.width * scale)), max(1, round(layer.height * scale))),
            Image.Resampling.LANCZOS,
        )
        chosen = (6, -line_count, rendered, layer)
        fitted_by_scaling = True

    chosen_size, negative_lines, rendered, layer = chosen
    width, height = layer.size
    px = area_left + (max_width - width) / 2 if centered else area_left
    desired_center_y = (y1 + y2) / 2
    py = max(area_top, min(area_bottom - height, desired_center_y - height / 2))
    crop.alpha_composite(layer, (round(px), round(py)))
    output_box = [round(px), round(py), round(px + width), round(py + height)]
    if output_box[0] < area_left or output_box[1] < area_top or output_box[2] > area_right or output_box[3] > area_bottom:
        raise RuntimeError(f"text overflow after fitting: {text!r} box={output_box} area={(area_left, area_top, area_right, area_bottom)}")
    return {
        "font_size": chosen_size,
        "line_count": -negative_lines,
        "rendered_text": rendered,
        "box": output_box,
        "available_box": [area_left, area_top, area_right, area_bottom],
        "canvas_size": [crop.width, crop.height],
        "fitted_by_scaling": fitted_by_scaling,
    }


def accepted_match(match: dict) -> bool:
    if match["rect_id"] in DENY_RECT_IDS:
        return False
    if match["chinese_translation"] == match["original_text"]:
        return False
    a, b = compact(match["original_text"]), compact(match["ocr_text"])
    if not a or not b:
        return False
    if len(b) == 1 and len(a) > 2:
        return False
    if len(b) / len(a) < 0.58:
        return False
    return match["match_score"] >= 0.78


def render_pbd_matches(images: dict[str, Image.Image], pbd_rows: dict[str, dict], matches: list[dict], log: list[dict]) -> None:
    for match in matches:
        if not accepted_match(match) or match["rect_id"] in MANUAL_RECT_TRANSLATIONS or match["rect_id"] == "R0065":
            continue
        row = pbd_rows[match["rect_id"]]
        image = images.setdefault(match["file_name"], Image.open(SOURCE_DIR / match["file_name"]).convert("RGBA"))
        group = best_ocr_group(row, match["original_text"])
        if group is None:
            continue
        view, items = group
        crop = logical_crop(image, row)
        box = source_bbox(match["rect_id"], row, view, items)
        color = pick_text_color(crop, box)
        erase_text(crop, box)
        rendered = draw_translation(
            crop,
            box,
            match["chinese_translation"],
            color,
            source_line_count=max(1, len(items)),
        )
        paste_logical_crop(image, row, crop)
        log.append({"kind": "pbd", **match, "source_box": list(box), "render": rendered, "color": list(color)})


def render_manual_pbd(images: dict[str, Image.Image], pbd_rows: dict[str, dict], log: list[dict]) -> None:
    manual = [
        ("R0005", "この機能が不要な場合は「OFF」を選択してください", "如果不需要此功能，请选择“OFF”。"),
        ("R0005", "システム設定画面でいつでも再設定が可能です。", "可随时在系统设置界面重新设置。"),
    ]
    manual.extend(
        (rect_id, values[0], values[1])
        for rect_id, values in MANUAL_RECT_TRANSLATIONS.items()
        if values is not None and rect_id != "R0005"
    )
    for rect_id, original, fallback_translation in manual:
        translation = translated_text(original, fallback_translation)
        row = pbd_rows[rect_id]
        file_name = f"{row['storage']}.png"
        image = images.setdefault(file_name, Image.open(SOURCE_DIR / file_name).convert("RGBA"))
        group = best_ocr_group(row, original)
        crop = logical_crop(image, row)
        if group is None:
            items = []
            box = (0, 0, crop.width, crop.height)
        else:
            view, items = group
            box = source_bbox(rect_id, row, view, items)
        color = pick_text_color(crop, box)
        # Text-only transparent menu states without OCR should keep the
        # established light-blue state color.
        if group is None and row["storage"].endswith("pulldown__pack"):
            color = (64, 128, 208, 255)
        erase_text(crop, box)
        rendered = draw_translation(crop, box, translation, color, source_line_count=1)
        paste_logical_crop(image, row, crop)
        log.append({"kind": "manual_pbd", "rect_id": rect_id, "file_name": file_name, "original_text": original, "chinese_translation": translation, "source_box": list(box), "render": rendered, "color": list(color)})


def render_manual_blocks(images: dict[str, Image.Image], log: list[dict]) -> None:
    # Four small Japanese help lines share one transparent atlas block.
    file_name = "system5__pack.png"
    image = images.setdefault(file_name, Image.open(SOURCE_DIR / file_name).convert("RGBA"))
    box = (0, 431, 580, 541)
    clear = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    text = (
        "在冒险画面中按住鼠标右键并向上下左右移动鼠标，\n"
        "即可执行对应功能。\n"
        "点击下拉菜单（▼）可更改手势项目。"
    )
    rendered = draw_translation(
        clear,
        (2, 2, clear.width - 2, clear.height - 2),
        text,
        (48, 64, 112, 255),
        font_path=SANS,
        source_line_count=3,
        forced_center=False,
    )
    image.paste(clear, (box[0], box[1]))
    log.append({"kind": "manual_block", "file_name": file_name, "box": list(box), "chinese_translation": text, "render": rendered})

    # Additional atlas labels that are present in a large PSD-derived base
    # sprite rather than in a separate PBD text state.
    direct = {
        "file__pack.png": [((316, 875, 543, 902), "チャプターとコメントを表示", "显示章节和备注", SANS, (64, 128, 208, 255), False)],
        "system1__pack.png": [
            ((40, 180, 345, 216), "日時ファイル名で保存", "以日期时间文件名保存", SANS, (64, 128, 208, 255), False),
            ((294, 360, 510, 392), "フルスクリーン", "全屏", SANS, (48, 48, 55, 255), False),
        ],
    }
    for target_file, items in direct.items():
        target = images.setdefault(target_file, Image.open(SOURCE_DIR / target_file).convert("RGBA"))
        for target_box, original_text, fallback_text, font_path, color, center in items:
            text_value = translated_text(original_text, fallback_text)
            rendered = edit_box(target, target_box, text_value, font_path, color, center=center)
            log.append({"kind": "direct_atlas", "file_name": target_file, "box": list(target_box), "original_text": original_text, "chinese_translation": text_value, "render": rendered})


def edit_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    font_path: Path,
    color: tuple[int, int, int, int],
    center: bool = False,
    lines: int = 1,
) -> dict:
    crop = image.crop(box).convert("RGBA")
    local_box = (0, 0, crop.width, crop.height)
    erase_text(crop, local_box)
    rendered = draw_translation(crop, local_box, text, color, font_path=font_path, source_line_count=lines, forced_center=center)
    image.paste(crop, (box[0], box[1]))
    return rendered


def render_popup_backgrounds(images: dict[str, Image.Image], log: list[dict]) -> None:
    specs = {
        "popup_system__bg0.png": [
            ((38, 38, 194, 63), "メッセージ速度", "文本速度"),
            ((39, 78, 200, 102), "オートプレイ速度", "自动播放速度"),
            ((38, 119, 201, 142), "ウィンドウ不透明度", "窗口不透明度"),
            ((37, 159, 165, 183), "未読スキップ", "跳过未读文本"),
        ],
        "popup_volume__bg0.png": [
            ((37, 39, 123, 63), "マスター", "主音量"),
            ((37, 120, 112, 142), "VOICE", "语音"),
            ((36, 160, 166, 183), "SE（ゲーム効果音）", "SE（游戏音效）"),
        ],
    }
    for file_name, items in specs.items():
        image = images.setdefault(file_name, Image.open(SOURCE_DIR / file_name).convert("RGBA"))
        for box, original_text, fallback_text in items:
            text = translated_text(original_text, fallback_text)
            # Paint the label area from the uniform panel color, then draw the Chinese serif label.
            panel = average_rgba(list(image.crop((20, box[1], 30, box[3])).getdata()))
            ImageDraw.Draw(image).rectangle(box, fill=panel)
            crop = image.crop(box).convert("RGBA")
            rendered = draw_translation(crop, (0, 0, crop.width, crop.height), text, (8, 8, 12, 255), font_path=SERIF, forced_center=False)
            image.paste(crop, (box[0], box[1]), crop)
            log.append({"kind": "popup", "file_name": file_name, "box": list(box), "original_text": original_text, "chinese_translation": text, "render": rendered})


def render_small_logos(images: dict[str, Image.Image], log: list[dict]) -> None:
    # Popup quick-save card.
    image = images.setdefault("popup_quick__bg0.png", Image.open(SOURCE_DIR / "popup_quick__bg0.png").convert("RGBA"))
    specs = [
        ((48, 58, 196, 88), "とける風花とシロうさぎ", "融化的风花与白兔", DECORATIVE, (72, 62, 110, 255), True),
        ((78, 94, 166, 112), "No Data", "无数据", SERIF, (135, 151, 177, 255), True),
    ]
    for box, original_text, fallback_text, font, color, center in specs:
        text = translated_text(original_text, fallback_text)
        rendered = edit_box(image, box, text, font, color, center=center)
        log.append({"kind": "small_logo", "file_name": "popup_quick__bg0.png", "box": list(box), "original_text": original_text, "chinese_translation": text, "render": rendered})

    # Save/load card embedded in file__pack. The Roman subtitle remains intact.
    image = images.setdefault("file__pack.png", Image.open(SOURCE_DIR / "file__pack.png").convert("RGBA"))
    for box, original_text, fallback_text, font, color, center in [
        ((588, 535, 832, 581), "とける風花とシロうさぎ", "融化的风花与白兔", DECORATIVE, (72, 62, 110, 255), True),
        ((660, 610, 753, 630), "No Data", "无数据", SERIF, (135, 151, 177, 255), True),
    ]:
        text = translated_text(original_text, fallback_text)
        rendered = edit_box(image, box, text, font, color, center=center)
        log.append({"kind": "small_logo", "file_name": "file__pack.png", "box": list(box), "original_text": original_text, "chinese_translation": text, "render": rendered})


def gradient_text_layer(size: tuple[int, int], text: str, font_path: Path, max_width: int, max_height: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    chosen = ImageFont.truetype(str(font_path), 20)
    for font_size in range(max_height, 20, -1):
        font = ImageFont.truetype(str(font_path), font_size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width and box[3] - box[1] <= max_height:
            chosen = font
            break
    box = draw.textbbox((0, 0), text, font=chosen)
    width, height = box[2] - box[0], box[3] - box[1]
    raw_mask = Image.new("L", (max(1, width), max(1, height)), 0)
    ImageDraw.Draw(raw_mask).text((-box[0], -box[1]), text, font=chosen, fill=255)
    if width > max_width or height > max_height:
        scale = min(max_width / max(1, width), max_height / max(1, height))
        raw_mask = raw_mask.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    px = (size[0] - raw_mask.width) // 2
    py = (size[1] - raw_mask.height) // 2
    mask.paste(raw_mask, (px, py))
    shadow = mask.filter(ImageFilter.GaussianBlur(7))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow_color = Image.new("RGBA", size, (105, 94, 155, 100))
    shadow_color.putalpha(shadow.point(lambda value: round(value * 0.42)))
    layer.alpha_composite(shadow_color)
    gradient = Image.new("RGBA", size)
    pixels = gradient.load()
    stops = [(0.0, (46, 39, 83)), (0.38, (163, 193, 229)), (0.62, (205, 151, 175)), (1.0, (47, 40, 83))]
    for x in range(size[0]):
        position = x / max(1, size[0] - 1)
        for index in range(len(stops) - 1):
            if stops[index][0] <= position <= stops[index + 1][0]:
                left, right = stops[index], stops[index + 1]
                factor = (position - left[0]) / max(1e-6, right[0] - left[0])
                color = tuple(round(left[1][c] * (1 - factor) + right[1][c] * factor) for c in range(3))
                break
        else:
            color = stops[-1][1]
        for y in range(size[1]):
            pixels[x, y] = (*color, 255)
    gradient.putalpha(mask)
    layer.alpha_composite(gradient)
    return layer


def render_title_art(images: dict[str, Image.Image], log: list[dict]) -> None:
    image = images.setdefault("title_bg_5.png", Image.open(SOURCE_DIR / "title_bg_5.png").convert("RGBA"))
    pixels = image.load()
    # Remove the Japanese title and its broad glow while retaining the alpha
    # silhouette of the original cloud-shaped backing.
    for y in range(35, 315):
        for x in range(55, 1480):
            r, g, b, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (255, 255, 255, a)
    font_path = DECORATIVE if DECORATIVE.exists() else FALLBACK_DECORATIVE
    title_text = translated_text("とける風花とシロうさぎ", "融化的风花与白兔")
    title_layer = gradient_text_layer((1420, 250), title_text, font_path, 1320, 205)
    image.alpha_composite(title_layer, (70, 65))
    decorations = ImageDraw.Draw(image)

    def snowflake(cx: int, cy: int, radius: int, color: tuple[int, int, int, int]) -> None:
        for angle in (0, 45, 90, 135):
            radians = math.radians(angle)
            dx = round(math.cos(radians) * radius)
            dy = round(math.sin(radians) * radius)
            decorations.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=color, width=4)

    snowflake(125, 275, 15, (185, 181, 226, 230))
    snowflake(1420, 270, 15, (181, 210, 235, 230))
    decorations.arc((105, 205, 710, 345), 5, 173, fill=(194, 185, 225, 210), width=6)
    log.append({"kind": "title_art", "file_name": "title_bg_5.png", "original_text": "とける風花とシロうさぎ", "chinese_translation": title_text})

    image = images.setdefault("title_bg_6.png", Image.open(SOURCE_DIR / "title_bg_6.png").convert("RGBA"))
    region = (105, 82, 392, 190)
    dominant = (42, 68, 107, 255)
    px = image.load()
    glyph_mask = Image.new("L", image.size, 0)
    gm = glyph_mask.load()
    for y in range(region[1], region[3]):
        for x in range(region[0], region[2]):
            r, g, b, a = px[x, y]
            if a > 30 and r + g + b > 560:
                gm[x, y] = 255
    glyph_mask = glyph_mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(2))
    fill = Image.new("RGBA", image.size, dominant)
    image.paste(fill, (0, 0), glyph_mask)
    text = translated_text("体験版", "体验版")
    title_crop = image.crop(region).convert("RGBA")
    rendered = draw_translation(
        title_crop,
        (0, 0, title_crop.width, title_crop.height),
        text,
        (255, 255, 255, 255),
        font_path=SANS,
        forced_center=True,
    )
    image.paste(title_crop, (region[0], region[1]), title_crop)
    log.append({"kind": "title_art", "file_name": "title_bg_6.png", "original_text": "体験版", "chinese_translation": text, "render": rendered})


def apply_custom_overrides(images: dict[str, Image.Image], log: list[dict]) -> None:
    if not CUSTOM_DIR.is_dir():
        return
    for path in sorted(CUSTOM_DIR.glob("*.png")):
        source_path = SOURCE_DIR / path.name
        if not source_path.is_file():
            raise FileNotFoundError(f"Custom uipsd override has no source image: {path.name}")
        with Image.open(source_path) as source, Image.open(path) as custom:
            if custom.size != source.size:
                raise ValueError(
                    f"Custom uipsd override dimensions changed: {path.name} "
                    f"({custom.width}x{custom.height}, expected {source.width}x{source.height})"
                )
            if custom.mode != source.mode:
                raise ValueError(
                    f"Custom uipsd override mode changed: {path.name} "
                    f"({custom.mode}, expected {source.mode})"
                )
            images[path.name] = custom.copy()
        log.append(
            {
                "kind": "custom_override",
                "file_name": path.name,
                "source": str(path),
            }
        )


def main() -> None:
    global SOURCE_DIR, BUILD_DIR, OUTPUT_DIR, OCR_PATH, MATCH_PATH, MANIFEST_PATH, TRANSLATION_PATH, CUSTOM_DIR
    parser = argparse.ArgumentParser(description="Render translated uipsd PNG atlases")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--build-dir", type=Path, default=BUILD_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--translations", type=Path)
    parser.add_argument("--custom-dir", type=Path, default=CUSTOM_DIR)
    args = parser.parse_args()
    SOURCE_DIR = args.source_dir.resolve()
    BUILD_DIR = args.build_dir.resolve()
    OUTPUT_DIR = (args.output_dir or (BUILD_DIR / "candidate_png")).resolve()
    OCR_PATH = BUILD_DIR / "pbd_rectangle_ocr.json"
    MATCH_PATH = BUILD_DIR / "pbd_translation_matches.json"
    MANIFEST_PATH = BUILD_DIR / "render_manifest.json"
    TRANSLATION_PATH = (args.translations or (BUILD_DIR / "translations_from_excel.json")).resolve()
    CUSTOM_DIR = args.custom_dir.resolve()
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(f"uipsd source directory not found: {SOURCE_DIR}")
    load_translation_lookup()
    pbd_payload = json.loads(OCR_PATH.read_text(encoding="utf-8"))
    match_payload = json.loads(MATCH_PATH.read_text(encoding="utf-8"))
    pbd_rows = {row["rect_id"]: row for row in pbd_payload["rows"]}
    images: dict[str, Image.Image] = {}
    log: list[dict] = []

    render_pbd_matches(images, pbd_rows, match_payload["matches"], log)
    render_manual_pbd(images, pbd_rows, log)
    render_manual_blocks(images, log)
    render_popup_backgrounds(images, log)
    render_small_logos(images, log)
    render_title_art(images, log)
    apply_custom_overrides(images, log)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.png"):
        stale.unlink()
    for file_name, image in sorted(images.items()):
        source = Image.open(SOURCE_DIR / file_name)
        if image.size != source.size:
            raise RuntimeError(f"dimension changed for {file_name}: {image.size} != {source.size}")
        image.save(OUTPUT_DIR / file_name)

    payload = {
        "source_directory": str(SOURCE_DIR),
        "output_directory": str(OUTPUT_DIR),
        "edited_file_count": len(images),
        "edit_count": len(log),
        "files": sorted(images),
        "edits": log,
    }
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"edited_files={len(images)} edits={len(log)}")
    print(OUTPUT_DIR)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
