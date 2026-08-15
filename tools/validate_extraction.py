#!/usr/bin/env python3
"""Validate the extracted archive and localization artifacts."""

import argparse
import csv
import json
import pathlib


SIGNATURES = {
    ".amv": (b"AJPM",),
    ".ogg": (b"OggS",),
    ".otf": (b"OTTO",),
    ".pbd": (b"TJS/",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".scn": (b"mdf\x00",),
    ".tlg": (b"TLG",),
    ".ttf": (b"\x00\x01\x00\x00", b"true", b"typ1"),
    ".wmv": (b"\x30\x26\xb2\x75\x8e\x66\xcf\x11",),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("extracted", type=pathlib.Path)
    parser.add_argument("localization", type=pathlib.Path)
    args = parser.parse_args()
    extracted = args.extracted.resolve()
    localization = args.localization.resolve()

    errors = []
    signature_counts = {ext: 0 for ext in SIGNATURES}
    status_counts = {}
    manifest_path = extracted / "_xp3_manifest.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))

    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
        path = extracted / pathlib.PurePosixPath(record["extracted_path"])
        if not path.is_file():
            errors.append(f"missing: {record['extracted_path']}")
            continue
        if path.stat().st_size != int(record["size"]):
            errors.append(f"size mismatch: {record['extracted_path']}")
        ext = pathlib.PurePosixPath(record["archive_name"]).suffix.lower()
        if ext in SIGNATURES:
            header = path.read_bytes()[:16]
            if not any(header.startswith(sig) for sig in SIGNATURES[ext]):
                errors.append(f"bad {ext} signature: {record['extracted_path']}")
            else:
                signature_counts[ext] += 1

    tlg_pngs = list((extracted / "_tlg_png").rglob("*.png"))
    bad_tlg_pngs = [
        str(path.relative_to(extracted))
        for path in tlg_pngs
        if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    ]
    errors.extend(f"bad converted PNG: {path}" for path in bad_tlg_pngs)

    scenario_jsons = sorted((extracted / "_scenario_decompiled").glob("*.txt.json"))
    scenario_entries = 0
    for path in scenario_jsons:
        document = json.loads(path.read_text(encoding="utf-8"))
        scenario_entries += sum(
            len(scene.get("texts", [])) for scene in document.get("scenes", [])
        )

    tjs_decompiled = list((localization / "tjs_decompiled").rglob("*.tjs"))
    for path in tjs_decompiled:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"decompiled TJS is not UTF-8: {path.relative_to(localization)}")

    utf8_texts = [
        path for path in (localization / "text_utf8").rglob("*") if path.is_file()
    ]
    for path in utf8_texts:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"UTF-8 text copy invalid: {path.relative_to(localization)}")

    table_path = localization / "scenario_dialogue_zh_cn.tsv"
    with table_path.open("r", encoding="utf-8-sig", newline="") as handle:
        dialogue_rows = list(csv.DictReader(handle, delimiter="\t"))

    report = {
        "result": "passed" if not errors else "failed",
        "manifest_records": len(records),
        "manifest_status_counts": status_counts,
        "signature_verified_counts": signature_counts,
        "tlg_png_previews": len(tlg_pngs),
        "scenario_json_files": len(scenario_jsons),
        "scenario_text_entries": scenario_entries,
        "scenario_translation_rows": len(dialogue_rows),
        "tjs_decompiled_files": len(tjs_decompiled),
        "utf8_text_copies": len(utf8_texts),
        "errors": errors,
    }
    report_path = extracted / "_verification_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
