from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OCR_PATH = ROOT / "build" / "uipsd_localize" / "pbd_rectangle_ocr.json"
WORKBOOK_DATA = ROOT / "build" / "uipsd_scan" / "workbook_data.json"
TRANSLATIONS = ROOT / "build" / "uipsd_localize" / "translations_from_excel.json"
OUTPUT_PATH = ROOT / "build" / "uipsd_localize" / "pbd_translation_matches.json"
REPORT_PATH = ROOT / "build" / "uipsd_localize" / "pbd_translation_matches.txt"


def compact(text: str) -> str:
    return re.sub(
        r"[\s・･／/()（）「」『』\[\].,。!?！？:*＊©×△▽▼→←ー—_\-]",
        "",
        str(text),
    ).lower()


def similarity(left: str, right: str) -> float:
    a, b = compact(left), compact(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        ratio = min(len(a), len(b)) / max(len(a), len(b))
        return 0.65 + ratio * 0.35
    return SequenceMatcher(None, a, b).ratio()


def ordered_texts(items: list[dict]) -> list[str]:
    return [
        item["text"]
        for item in sorted(items, key=lambda row: (row["box"][1], row["box"][0]))
        if item.get("text")
    ]


def candidates_for_row(row: dict) -> list[str]:
    candidates: list[str] = []
    for view in ("light", "dark"):
        texts = ordered_texts(row["ocr"].get(view, []))
        candidates.extend(texts)
        if len(texts) > 1:
            candidates.append("".join(texts))
    return list(dict.fromkeys(candidates))


def main() -> None:
    ocr = json.loads(OCR_PATH.read_text(encoding="utf-8"))
    workbook = json.loads(WORKBOOK_DATA.read_text(encoding="utf-8"))
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    chinese_by_id = {
        row["id"]: (row["chinese_translation"] or row["original_text"])
        for row in translations["rows"]
    }

    catalog_by_file: dict[str, list[dict]] = {}
    for item in workbook["translations"]:
        catalog_by_file.setdefault(item["file_name"], []).append(item)

    matches = []
    matched_ids_by_file: dict[str, set[str]] = {}
    for row in ocr["rows"]:
        file_name = f"{row['storage']}.png"
        catalog = catalog_by_file.get(file_name, [])
        candidates = candidates_for_row(row)
        ranked = []
        for item in catalog:
            best_score = 0.0
            best_ocr = ""
            for candidate in candidates:
                score = similarity(item["original_text"], candidate)
                if score > best_score:
                    best_score = score
                    best_ocr = candidate
            ranked.append((best_score, item, best_ocr))
        ranked.sort(key=lambda value: value[0], reverse=True)
        if not ranked or ranked[0][0] < 0.66:
            continue
        score, item, best_ocr = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        # Ambiguous single-token ON/OFF/state crops need a stronger margin.
        if score < 0.82 and score - second_score < 0.12:
            continue
        match = {
            "rect_id": row["rect_id"],
            "file_name": file_name,
            "storage": row["storage"],
            "x": row["x"],
            "y": row["y"],
            "width": row["width"],
            "height": row["height"],
            "rotated": row["rotated"],
            "uses": row["uses"],
            "id": item["id"],
            "original_text": item["original_text"],
            "chinese_translation": chinese_by_id[item["id"]],
            "ocr_text": best_ocr,
            "match_score": round(score, 4),
            "second_score": round(second_score, 4),
        }
        matches.append(match)
        matched_ids_by_file.setdefault(file_name, set()).add(item["id"])

    unresolved = []
    for file_name, catalog in sorted(catalog_by_file.items()):
        matched = matched_ids_by_file.get(file_name, set())
        for item in catalog:
            if item["id"] not in matched:
                unresolved.append(
                    {
                        "file_name": file_name,
                        "id": item["id"],
                        "original_text": item["original_text"],
                        "chinese_translation": chinese_by_id[item["id"]],
                    }
                )

    payload = {
        "match_count": len(matches),
        "matched_file_id_count": sum(len(ids) for ids in matched_ids_by_file.values()),
        "unresolved_count": len(unresolved),
        "matches": matches,
        "unresolved": unresolved,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"matches={len(matches)} matched_file_ids={payload['matched_file_id_count']} unresolved={len(unresolved)}",
        "",
    ]
    for file_name in sorted({row["file_name"] for row in matches}):
        lines.append(f"## {file_name}")
        for row in [item for item in matches if item["file_name"] == file_name]:
            lines.append(
                f"{row['rect_id']} [{row['x']},{row['y']} {row['width']}x{row['height']}] "
                f"{row['id']} {row['ocr_text']} => {row['chinese_translation']} "
                f"score={row['match_score']}"
            )
        lines.append("")
    lines.append("## UNRESOLVED")
    for row in unresolved:
        lines.append(
            f"{row['file_name']} {row['id']} {row['original_text']} => {row['chinese_translation']}"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(lines[0])
    print(OUTPUT_PATH)
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
