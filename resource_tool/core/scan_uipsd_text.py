from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "extracted" / "_tlg_png" / "uipsd"
OUTPUT_DIR = ROOT / "build" / "uipsd_scan"


def resolve_ocr_environment() -> tuple[Path, Path]:
    runtime_override = os.environ.get("KAZESHIRO_PADDLEOCR_RUNTIME")
    model_override = os.environ.get("KAZESHIRO_OCR_MODEL_HOME")
    candidates: list[tuple[Path, Path]] = []
    if runtime_override:
        runtime = Path(runtime_override).expanduser().resolve()
        model_home = (
            Path(model_override).expanduser().resolve()
            if model_override
            else runtime.parent
        )
        candidates.append((runtime, model_home))

    for ancestor in (ROOT, *ROOT.parents):
        tool_home = ancestor / "translate_tool"
        candidates.append((tool_home / "paddleocr_runtime", tool_home))
        if tool_home.is_dir():
            for backup in sorted(
                tool_home.glob(".cleanup-backup-*/root-unused"), reverse=True
            ):
                candidates.append((backup / "paddleocr_runtime", backup))

    for runtime, model_home in candidates:
        if (runtime / "paddleocr" / "__init__.py").is_file():
            if model_override:
                model_home = Path(model_override).expanduser().resolve()
            return runtime, model_home

    checked = "\n".join(f"  - {runtime}" for runtime, _ in candidates)
    raise FileNotFoundError(
        "未找到 PaddleOCR 运行库。可设置 KAZESHIRO_PADDLEOCR_RUNTIME；"
        f"已检查：\n{checked}"
    )


RUNTIME_DIR, MODEL_HOME = resolve_ocr_environment()
GPU_RUNTIME_DIR = Path(
    os.environ.get(
        "KAZESHIRO_PADDLE_GPU_RUNTIME",
        str(ROOT / "runtime" / "paddle_gpu_runtime"),
    )
).expanduser().resolve()

os.environ["PADDLE_HOME"] = str(MODEL_HOME / "paddle_home")
os.environ["PADDLEX_HOME"] = str(MODEL_HOME / "paddlex_home")
os.environ["PADDLE_PDX_CACHE_HOME"] = str(MODEL_HOME / ".paddlex")
os.environ["USERPROFILE"] = str(MODEL_HOME)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def detect_nvidia_gpus() -> list[dict[str, object]]:
    executable = shutil.which("nvidia-smi.exe") or shutil.which("nvidia-smi")
    if not executable:
        return []
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=index,name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    result: list[dict[str, object]] = []
    for line in completed.stdout.splitlines():
        if not line.strip() or "," not in line:
            continue
        index_text, name = line.split(",", 1)
        try:
            index = int(index_text.strip())
        except ValueError:
            continue
        result.append({"index": index, "name": name.strip()})
    return result


def is_supported_rtx(name: str) -> bool:
    return bool(re.search(r"\bRTX\s+(?:40|50)\d{2}\b", name, re.IGNORECASE))


def gpu_dll_directories(gpu_runtime: Path) -> list[Path]:
    nvidia = gpu_runtime / "nvidia"
    if not nvidia.is_dir():
        return []
    return sorted(path for path in nvidia.glob("*/bin") if path.is_dir())


def probe_gpu_runtime(gpu_runtime: Path, device_index: int) -> tuple[bool, str]:
    if not (gpu_runtime / "paddle" / "__init__.py").is_file():
        return False, f"GPU 运行库不存在：{gpu_runtime}"
    probe = (
        "import paddle; "
        "assert paddle.device.is_compiled_with_cuda(), 'not a CUDA build'; "
        "assert paddle.device.cuda.device_count() > 0, 'no CUDA device'; "
        f"paddle.set_device('gpu:{device_index}'); "
        "x=paddle.ones([1,3,16,16]); "
        "w=paddle.ones([4,3,3,3]); "
        "y=paddle.nn.functional.conv2d(x,w); "
        "assert tuple(y.shape) == (1,4,14,14); "
        "assert float(y.mean().numpy()) > 0; "
        "print(paddle.__version__)"
    )
    env = os.environ.copy()
    paths = [str(gpu_runtime), str(RUNTIME_DIR)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    dll_paths = [str(path) for path in gpu_dll_directories(gpu_runtime)]
    env["PATH"] = os.pathsep.join(dll_paths + [env.get("PATH", "")])
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            env=env,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
        return False, detail.strip().splitlines()[-1] if detail.strip() else str(exc)
    return True, completed.stdout.strip().splitlines()[-1]


def choose_ocr_device() -> tuple[str, dict[str, object]]:
    preference = os.environ.get("KAZESHIRO_OCR_DEVICE", "auto").strip().lower()
    names = detect_nvidia_gpus()
    supported = [gpu for gpu in names if is_supported_rtx(str(gpu["name"]))]
    info: dict[str, object] = {
        "preference": preference,
        "nvidia_gpus": names,
        "supported_rtx_40_50": supported,
        "gpu_runtime": str(GPU_RUNTIME_DIR),
    }
    if preference == "cpu":
        info["reason"] = "KAZESHIRO_OCR_DEVICE=cpu"
        return "cpu", info
    if not supported:
        info["reason"] = "未检测到 RTX 40/50 系列显卡"
        return "cpu", info
    selected = supported[0]
    device_index = int(selected["index"])
    usable, detail = probe_gpu_runtime(GPU_RUNTIME_DIR, device_index)
    info["gpu_probe"] = detail
    if not usable:
        info["reason"] = "GPU 运行库自检失败，已回退 CPU"
        return "cpu", info
    info["selected_gpu"] = selected
    info["reason"] = f"检测到受支持显卡：{selected['name']}"
    return f"gpu:{device_index}", info


OCR_DEVICE, GPU_INFO = choose_ocr_device()
sys.path.insert(0, str(RUNTIME_DIR))
GPU_DLL_HANDLES: list[object] = []
if OCR_DEVICE.startswith("gpu"):
    dll_paths = gpu_dll_directories(GPU_RUNTIME_DIR)
    os.environ["PATH"] = os.pathsep.join(
        [str(path) for path in dll_paths] + [os.environ.get("PATH", "")]
    )
    if hasattr(os, "add_dll_directory"):
        GPU_DLL_HANDLES = [os.add_dll_directory(str(path)) for path in dll_paths]
    sys.path.insert(0, str(GPU_RUNTIME_DIR))

from paddleocr import PaddleOCR  # noqa: E402


CANDIDATES = [
    "backlog__pack.png",
    "dialog__pack.png",
    "extra_cg__bg0.png",
    "extra_cg__pack.png",
    "extra_music__bg0.png",
    "extra_music__pack.png",
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
    "system0__pack.png",
    "title__pack.png",
    "title_bg_2.png",
    "title_bg_5.png",
    "title_bg_6.png",
]

SCAN_ROTATIONS = (0, 90, 270)
DEFAULT_FULL_ROTATION_MAX_PIXELS = 2_500_000


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


def rotate_for_scan(image: Image.Image, rotation_degrees: int) -> Image.Image:
    if rotation_degrees == 0:
        return image
    if rotation_degrees == 90:
        return image.transpose(Image.Transpose.ROTATE_90)
    if rotation_degrees == 270:
        return image.transpose(Image.Transpose.ROTATE_270)
    raise ValueError(f"unsupported OCR rotation: {rotation_degrees}")


def clockwise_read_rotation(rotation_degrees: int) -> int:
    """Return the clockwise turn a human should apply to read this text."""
    if rotation_degrees == 0:
        return 0
    # PIL's ROTATE_90/ROTATE_270 constants are counter-clockwise rotations.
    return (360 - rotation_degrees) % 360


def read_direction(rotation_degrees: int) -> str:
    return {
        0: "normal",
        90: "rotate_counterclockwise_90",
        270: "rotate_clockwise_90",
    }[rotation_degrees]


def box_to_original(
    box: tuple[int, int, int, int],
    original_size: tuple[int, int],
    rotation_degrees: int,
) -> tuple[int, int, int, int]:
    """Map a box from an OCR-rotated image back to the source PNG."""
    x1, y1, x2, y2 = box
    width, height = original_size
    if rotation_degrees == 0:
        result = box
    elif rotation_degrees == 90:
        result = (width - y2, x1, width - y1, x2)
    elif rotation_degrees == 270:
        result = (y1, height - x2, y2, height - x1)
    else:
        raise ValueError(f"unsupported OCR rotation: {rotation_degrees}")
    return (
        max(0, min(width - 1, result[0])),
        max(0, min(height - 1, result[1])),
        max(1, min(width, result[2])),
        max(1, min(height, result[3])),
    )


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


def intersection_area(a: dict, b: dict) -> int:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    width = max(0, min(ax2, bx2) - max(a["x"], b["x"]))
    height = max(0, min(ay2, by2) - max(a["y"], b["y"]))
    return width * height


def union_area(rectangles: list[tuple[int, int, int, int]]) -> int:
    """Calculate a small rectangle set's exact union area."""
    if not rectangles:
        return 0
    x_edges = sorted({edge for rect in rectangles for edge in (rect[0], rect[2])})
    area = 0
    for left, right in zip(x_edges, x_edges[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (top, bottom)
            for x1, top, x2, bottom in rectangles
            if x1 < right and x2 > left and bottom > top
        )
        if not intervals:
            continue
        merged_height = 0
        current_top, current_bottom = intervals[0]
        for top, bottom in intervals[1:]:
            if top <= current_bottom:
                current_bottom = max(current_bottom, bottom)
            else:
                merged_height += current_bottom - current_top
                current_top, current_bottom = top, bottom
        merged_height += current_bottom - current_top
        area += (right - left) * merged_height
    return area


def japanese_character_counts(text: str) -> tuple[int, int]:
    kana = 0
    cjk = 0
    for character in text:
        codepoint = ord(character)
        if 0x3040 <= codepoint <= 0x30FF or 0x31F0 <= codepoint <= 0x31FF:
            kana += 1
        elif 0x3400 <= codepoint <= 0x9FFF:
            cjk += 1
    return kana, cjk


def detection_quality(row: dict) -> float:
    text = normalize_text(row["text"])
    kana, cjk = japanese_character_counts(text)
    useful_length = min(len(text), 28)
    language_bonus = kana * 1.35 + cjk * 0.35
    short_penalty = 2.0 if len(text) <= 1 else 0.0
    return (
        float(row["confidence"]) * (2.0 + useful_length + language_bonus)
        - short_penalty
    )


def same_vertical_line(a: dict, b: dict) -> bool:
    center_a = a["x"] + a["width"] / 2
    center_b = b["x"] + b["width"] / 2
    if abs(center_a - center_b) > max(8.0, min(a["width"], b["width"]) * 0.45):
        return False
    top = max(a["y"], b["y"])
    bottom = min(a["y"] + a["height"], b["y"] + b["height"])
    smaller_height = min(a["height"], b["height"])
    return smaller_height > 0 and (bottom - top) / smaller_height >= 0.45


def collapse_vertical_fragments(rows: list[dict]) -> list[dict]:
    """Prefer the most complete OCR result for each vertical source line."""
    selected: list[dict] = []
    for candidate in sorted(rows, key=detection_quality, reverse=True):
        if not any(same_vertical_line(candidate, existing) for existing in selected):
            selected.append(candidate)
    return sorted(selected, key=lambda item: (item["x"], item["y"]))


def rotated_pass_score(rows: list[dict]) -> float:
    return round(sum(max(0.0, detection_quality(row)) for row in rows), 3)


def covered_by_vertical_text(candidate: dict, vertical_rows: list[dict]) -> bool:
    """Detect normal-pass garbage crossing one or more corrected vertical lines."""
    intersections: list[tuple[int, int, int, int]] = []
    for vertical in vertical_rows:
        x1 = max(candidate["x"], vertical["x"])
        y1 = max(candidate["y"], vertical["y"])
        x2 = min(
            candidate["x"] + candidate["width"],
            vertical["x"] + vertical["width"],
        )
        y2 = min(
            candidate["y"] + candidate["height"],
            vertical["y"] + vertical["height"],
        )
        if x2 > x1 and y2 > y1:
            intersections.append((x1, y1, x2, y2))
    candidate_area = candidate["width"] * candidate["height"]
    return candidate_area > 0 and union_area(intersections) / candidate_area >= 0.20


def select_mixed_orientations(rows: list[dict]) -> tuple[list[dict], dict]:
    """Keep normal text plus the automatically selected vertical read direction."""
    normal_rows = [row for row in rows if row.get("rotation_degrees", 0) == 0]
    rotated_groups = {
        rotation: collapse_vertical_fragments(
            [row for row in rows if row.get("rotation_degrees") == rotation]
        )
        for rotation in SCAN_ROTATIONS[1:]
    }
    scores = {
        rotation: rotated_pass_score(group)
        for rotation, group in rotated_groups.items()
    }
    best_rotation = max(scores, key=scores.get) if any(scores.values()) else 0
    selected_vertical = rotated_groups.get(best_rotation, [])
    clean_normal = [
        row
        for row in normal_rows
        if not covered_by_vertical_text(row, selected_vertical)
    ]
    metadata = {
        "vertical_rotation_scores": {str(key): value for key, value in scores.items()},
        "selected_vertical_rotation_degrees": best_rotation,
        "selected_read_rotation_clockwise_degrees": (
            clockwise_read_rotation(best_rotation) if best_rotation else 0
        ),
    }
    return deduplicate(clean_normal + selected_vertical), metadata


def color_distance_squared(
    left: tuple[int, int, int], right: tuple[int, int, int]
) -> int:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def is_transparency_key(red: int, green: int, blue: int) -> bool:
    """Ignore the magenta chroma key used by a few unpacked UI atlases."""
    return red > 185 and blue > 125 and green < 105


def border_background_colors(
    pixels: list[tuple[int, int, int, int]], width: int, height: int
) -> list[tuple[int, int, int]]:
    """Estimate opaque backgrounds from a thin ring inside the OCR box."""
    thickness = max(1, min(3, min(width, height) // 10))
    bins: Counter[tuple[int, int, int]] = Counter()
    sums: dict[tuple[int, int, int], list[int]] = {}
    for y in range(height):
        for x in range(width):
            if (
                x >= thickness
                and x < width - thickness
                and y >= thickness
                and y < height - thickness
            ):
                continue
            red, green, blue, alpha = pixels[y * width + x]
            if alpha < 48 or is_transparency_key(red, green, blue):
                continue
            key = (red // 16, green // 16, blue // 16)
            bins[key] += 1
            total = sums.setdefault(key, [0, 0, 0, 0])
            total[0] += red
            total[1] += green
            total[2] += blue
            total[3] += 1
    if not bins:
        return []
    minimum = max(2, round(sum(bins.values()) * 0.025))
    result: list[tuple[int, int, int]] = []
    for key, count in bins.most_common(8):
        if count < minimum and result:
            continue
        red, green, blue, samples = sums[key]
        result.append((red // samples, green // samples, blue // samples))
    return result


def foreground_depth(mask: list[bool], width: int, height: int) -> list[int]:
    """Measure how far each foreground pixel is from its outer boundary.

    Text fill normally lies inside its outline, while antialiasing, outlines,
    shadows and leftover background pixels stay close to the boundary.
    """
    active = mask[:]
    depths = [0] * len(mask)
    for level in range(1, 9):
        if not any(active):
            break
        next_active = [False] * len(mask)
        for y in range(height):
            row = y * width
            for x in range(width):
                index = row + x
                if not active[index]:
                    continue
                depths[index] = level
                if x == 0 or y == 0 or x + 1 == width or y + 1 == height:
                    continue
                if (
                    active[index - 1]
                    and active[index + 1]
                    and active[index - width]
                    and active[index + width]
                ):
                    next_active[index] = True
        active = next_active
    return depths


def palette_for_box(image: Image.Image, box: dict) -> list[str]:
    rgba = image.convert("RGBA")
    x1 = max(0, box["x"])
    y1 = max(0, box["y"])
    x2 = min(rgba.width, x1 + max(1, box["width"]))
    y2 = min(rgba.height, y1 + max(1, box["height"]))
    crop = rgba.crop((x1, y1, x2, y2))
    width, height = crop.size
    pixels = list(crop.getdata())
    visible = [
        alpha >= 48 and not is_transparency_key(red, green, blue)
        for red, green, blue, alpha in pixels
    ]
    if not any(visible):
        return ["#202020"]

    transparent_ratio = 1.0 - sum(visible) / len(visible)
    if transparent_ratio >= 0.02:
        foreground = visible
    else:
        backgrounds = border_background_colors(pixels, width, height)
        foreground = []
        for is_visible, (red, green, blue, _alpha) in zip(visible, pixels):
            different = not backgrounds or min(
                color_distance_squared((red, green, blue), background)
                for background in backgrounds
            ) >= 30**2
            foreground.append(is_visible and different)
        minimum_foreground = max(4, round(len(pixels) * 0.005))
        if sum(foreground) < minimum_foreground:
            foreground = visible

    depths = foreground_depth(foreground, width, height)
    clusters: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = {}
    for index, ((red, green, blue, alpha), is_foreground) in enumerate(
        zip(pixels, foreground)
    ):
        if not is_foreground:
            continue
        key = (red // 12, green // 12, blue // 12)
        clusters.setdefault(key, []).append((red, green, blue, alpha, depths[index]))

    ranked: list[tuple[float, tuple[int, int, int]]] = []
    for samples in clusters.values():
        if len(samples) < 2 and len(pixels) > 20:
            continue
        max_depth = max(sample[4] for sample in samples)
        opacity = sum(sample[3] / 255.0 for sample in samples)
        average_depth = (
            sum((sample[3] / 255.0) * sample[4] for sample in samples)
            / max(opacity, 0.001)
        )
        # A flat count favors a thick outline.  Average stroke depth favors
        # the enclosed fill, while logarithmic support keeps tiny antialias
        # shades from winning merely because one or two pixels are deep.
        score = average_depth**3 * math.log2(1.0 + opacity)
        core_samples = [
            sample
            for sample in samples
            if sample[3] >= 160 and sample[4] >= max(1, max_depth - 1)
        ] or samples
        exact = Counter((red, green, blue) for red, green, blue, _a, _d in core_samples)
        representative = exact.most_common(1)[0][0]
        ranked.append((score, representative))

    if not ranked:
        exact = Counter(
            (red, green, blue)
            for (red, green, blue, _alpha), keep in zip(pixels, visible)
            if keep
        )
        ranked = [(float(count), color) for color, count in exact.most_common(4)]

    result: list[str] = []
    for _score, (red, green, blue) in sorted(ranked, reverse=True):
        value = f"#{red:02X}{green:02X}{blue:02X}"
        if value not in result:
            result.append(value)
        if len(result) == 4:
            break
    return result or ["#202020"]


def parse_result(
    result: dict,
    original: Image.Image,
    scaled_width: int,
    gap: int,
    scale: float,
    rotation_degrees: int,
    source_offset: tuple[int, int] = (0, 0),
    palette_image: Image.Image | None = None,
) -> list[dict]:
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
        oriented_box = (
            max(0, round(x1 / scale)),
            max(0, round(y1 / scale)),
            max(1, round(x2 / scale)),
            max(1, round(y2 / scale)),
        )
        mapped = box_to_original(oriented_box, original.size, rotation_degrees)
        mapped_width = max(1, mapped[2] - mapped[0])
        mapped_height = max(1, mapped[3] - mapped[1])
        box = {
            "x": mapped[0] + source_offset[0],
            "y": mapped[1] + source_offset[1],
            "width": mapped_width,
            "height": mapped_height,
        }
        # The 90-degree passes exist specifically for text that occupies a
        # portrait-shaped region in the original atlas. Discard accidental
        # OCR of normal horizontal text after the whole image is rotated.
        if rotation_degrees and box["height"] <= box["width"] * 1.15:
            continue
        row = {
            **box,
            "text": normalized,
            "confidence": round(float(scores[index]), 4),
            "orientation": (
                "vertical_source"
                if rotation_degrees
                else (
                    "vertical"
                    if box["height"] > box["width"] * 1.8
                    else "horizontal"
                )
            ),
            "rotation_degrees": rotation_degrees,
            "read_direction": read_direction(rotation_degrees),
            "read_rotation_clockwise_degrees": clockwise_read_rotation(
                rotation_degrees
            ),
            "angle": int(angles[index]) if index < len(angles) else -1,
            "source_view": source_view,
            "font_size_estimate_px": max(
                1, round((oriented_box[3] - oriented_box[1]) * 0.82)
            ),
        }
        row["palette"] = palette_for_box(palette_image or original, row)
        rows.append(row)

    return rows


def deduplicate(rows: list[dict]) -> list[dict]:
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


def rotated_candidate_regions(
    detections: list[dict], image_size: tuple[int, int]
) -> list[dict]:
    image_width, image_height = image_size
    candidates: list[dict] = []
    for detection in detections:
        if detection["height"] <= detection["width"] * 1.35:
            continue
        padding = max(3, round(min(detection["width"], detection["height"]) * 0.20))
        x1 = max(0, detection["x"] - padding)
        y1 = max(0, detection["y"] - padding)
        x2 = min(image_width, detection["x"] + detection["width"] + padding)
        y2 = min(image_height, detection["y"] + detection["height"] + padding)
        candidates.append(
            {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
        )

    regions: list[dict] = []
    for candidate in sorted(
        candidates, key=lambda row: row["width"] * row["height"], reverse=True
    ):
        if not any(overlaps(candidate, existing) for existing in regions):
            regions.append(candidate)
    return sorted(regions, key=lambda row: (row["y"], row["x"]))


def scan_rotated_regions(
    ocr: PaddleOCR,
    original: Image.Image,
    base_detections: list[dict],
    prepared_dir: Path,
    file_name: str,
) -> list[dict]:
    detections: list[dict] = []
    regions = rotated_candidate_regions(base_detections, original.size)
    for region_index, region in enumerate(regions, start=1):
        region_box = (
            region["x"],
            region["y"],
            region["x"] + region["width"],
            region["y"] + region["height"],
        )
        source_crop = original.crop(region_box)
        for rotation_degrees in SCAN_ROTATIONS[1:]:
            oriented = rotate_for_scan(source_crop, rotation_degrees)
            prepared, scaled_width, gap, scale = composite_pair(oriented)
            prepared_path = prepared_dir / (
                f"{Path(file_name).stem}.region{region_index:03d}."
                f"rot{rotation_degrees:03d}.png"
            )
            prepared.save(prepared_path)
            prediction = ocr.predict(str(prepared_path))
            detections.extend(
                parse_result(
                    prediction[0],
                    source_crop,
                    scaled_width=scaled_width,
                    gap=gap,
                    scale=scale,
                    rotation_degrees=rotation_degrees,
                    source_offset=(region["x"], region["y"]),
                    palette_image=original,
                )
            )
    return detections


def scan_whole_orientation(
    ocr: PaddleOCR,
    original: Image.Image,
    prepared_dir: Path,
    file_name: str,
    rotation_degrees: int,
) -> list[dict]:
    """OCR one whole atlas orientation and map boxes to the source coordinates."""
    oriented = rotate_for_scan(original, rotation_degrees)
    prepared, scaled_width, gap, scale = composite_pair(oriented)
    prepared_path = prepared_dir / (
        f"{Path(file_name).stem}.full.rot{rotation_degrees:03d}.png"
    )
    prepared.save(prepared_path)
    prediction = ocr.predict(str(prepared_path))
    return parse_result(
        prediction[0],
        original,
        scaled_width=scaled_width,
        gap=gap,
        scale=scale,
        rotation_degrees=rotation_degrees,
    )


def selected_candidates(requested: list[str] | None) -> list[str]:
    if not requested:
        return CANDIDATES
    names: list[str] = []
    for value in requested:
        for raw_name in value.split(","):
            name = raw_name.strip()
            if not name:
                continue
            if not name.lower().endswith(".png"):
                name += ".png"
            if name not in names:
                names.append(name)
    return names


def main(argv: list[str] | None = None) -> None:
    global SOURCE_DIR, OUTPUT_DIR
    parser = argparse.ArgumentParser(description="Scan uipsd PNG text with local OCR")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--files",
        action="append",
        help="只扫描指定 PNG；可重复使用或用逗号分隔",
    )
    parser.add_argument(
        "--full-rotation-max-pixels",
        type=int,
        default=DEFAULT_FULL_ROTATION_MAX_PIXELS,
        help=(
            "在此像素数以内对整张图自动尝试三个方向；"
            "更大的图回退到候选区域扫描（设为 0 可强制所有图片整图扫描）"
        ),
    )
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
    print(f"OCR_DEVICE={OCR_DEVICE}", flush=True)
    print(f"OCR_DEVICE_REASON={GPU_INFO['reason']}", flush=True)
    ocr = PaddleOCR(
        lang="japan",
        device=OCR_DEVICE,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_rec_score_thresh=0.35,
    )
    candidates = selected_candidates(args.files)
    all_results: list[dict] = []
    for index, file_name in enumerate(candidates, start=1):
        source_path = SOURCE_DIR / file_name
        if not source_path.is_file():
            raise FileNotFoundError(f"uipsd PNG not found: {source_path}")
        original = Image.open(source_path)
        base_detections = scan_whole_orientation(
            ocr, original, prepared_dir, file_name, rotation_degrees=0
        )
        scan_whole = (
            args.full_rotation_max_pixels <= 0
            or original.width * original.height <= args.full_rotation_max_pixels
        )
        if scan_whole:
            detections = list(base_detections)
            for rotation_degrees in SCAN_ROTATIONS[1:]:
                detections.extend(
                    scan_whole_orientation(
                        ocr,
                        original,
                        prepared_dir,
                        file_name,
                        rotation_degrees=rotation_degrees,
                    )
                )
            direction_method = "whole_image_multi_pass"
        else:
            detections = base_detections + scan_rotated_regions(
                ocr, original, base_detections, prepared_dir, file_name
            )
            direction_method = "region_multi_pass"
        detections, direction_summary = select_mixed_orientations(detections)
        for detection in detections:
            detection["direction_detection"] = direction_method
        all_results.append(
            {
                "file_name": file_name,
                "width": original.width,
                "height": original.height,
                "direction_detection": direction_method,
                **direction_summary,
                "detections": detections,
            }
        )
        rotated_count = sum(
            1 for item in detections if item.get("rotation_degrees", 0)
        )
        print(
            f"[{index:02d}/{len(candidates):02d}] {file_name}: "
            f"detections={len(detections)} rotated={rotated_count}",
            flush=True,
        )

    output_path = OUTPUT_DIR / "ocr_results.json"
    output_path.write_text(
        json.dumps(
            {
                "source_directory": str(SOURCE_DIR),
                "candidate_count": len(candidates),
                "ocr_device": OCR_DEVICE,
                "gpu_detection": GPU_INFO,
                "scan_rotations": list(SCAN_ROTATIONS),
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
