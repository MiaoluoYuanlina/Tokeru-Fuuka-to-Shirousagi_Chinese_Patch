#!/usr/bin/env python3
"""Build UTF-8 text copies and a scenario translation table."""

import argparse
import csv
import json
import pathlib
import struct
import zlib


TEXT_EXTENSIONS = {
    ".asd",
    ".csv",
    ".func",
    ".ini",
    ".ks",
    ".sinfo",
    ".sli",
    ".stage",
    ".stand",
    ".tjs",
    ".txt",
}


def decode_text(data):
    if data.startswith(b"\xfe\xfe\x02\xff\xfe") and len(data) >= 21:
        packed_size, original_size = struct.unpack_from("<QQ", data, 5)
        payload = data[21:21 + packed_size]
        decoded = zlib.decompress(payload)
        if len(decoded) != original_size:
            raise UnicodeError("压缩 TJS 的解压长度不匹配")
        return decoded.decode("utf-16le"), "kirikiri-compressed-utf16le"
    if data.startswith(b"TJS2100"):
        raise UnicodeError("TJS2100 编译字节码（源码见 tjs_decompiled）")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16le"), "utf-16le"
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16be"), "utf-16be"
    if data.count(b"\x00") > max(8, len(data) // 20):
        raise UnicodeError("疑似二进制文件")
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp932"), "cp932"


def write_utf8_copies(extracted_root, localization_root):
    output_root = localization_root / "text_utf8"
    rows = []
    converted = 0
    skipped = 0
    for source in sorted(extracted_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if "_scenario_decompiled" in source.parts:
            continue
        relative = source.relative_to(extracted_root)
        destination = output_root / relative
        try:
            text, encoding = decode_text(source.read_bytes())
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            status = "converted"
            converted += 1
        except (UnicodeError, UnicodeDecodeError) as exc:
            encoding = ""
            destination = None
            status = f"skipped: {exc}"
            skipped += 1
        rows.append(
            {
                "source_path": relative.as_posix(),
                "utf8_path": (
                    destination.relative_to(localization_root).as_posix()
                    if destination else ""
                ),
                "source_encoding": encoding,
                "source_bytes": source.stat().st_size,
                "status": status,
            }
        )

    inventory = localization_root / "text_inventory.csv"
    with inventory.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return rows, converted, skipped


def voice_names(voice_data):
    if not isinstance(voice_data, list):
        return ""
    result = []
    for item in voice_data:
        if isinstance(item, dict) and item.get("voice"):
            result.append(str(item["voice"]))
    return ",".join(result)


def build_scenario_table(extracted_root, localization_root):
    scenario_root = extracted_root / "_scenario_decompiled"
    rows = []
    files = []
    text_entries = 0
    for source in sorted(scenario_root.glob("*.txt.json")):
        document = json.loads(source.read_text(encoding="utf-8"))
        file_entries = 0
        for scene_index, scene in enumerate(document.get("scenes", [])):
            label = scene.get("label", "")
            for text_index, entry in enumerate(scene.get("texts", [])):
                text_entries += 1
                file_entries += 1
                if not isinstance(entry, list):
                    continue
                speaker = entry[0] if len(entry) > 0 and entry[0] is not None else ""
                segments = entry[1] if len(entry) > 1 and isinstance(entry[1], list) else []
                voices = voice_names(entry[2] if len(entry) > 2 else None)
                for segment_index, segment in enumerate(segments):
                    if not isinstance(segment, list):
                        continue
                    prefix = segment[0] if len(segment) > 0 and segment[0] is not None else ""
                    text = segment[1] if len(segment) > 1 and segment[1] is not None else ""
                    if not isinstance(text, str):
                        continue
                    rows.append(
                        {
                            "source_file": source.name,
                            "scene_index": scene_index,
                            "scene_label": label,
                            "text_index": text_index,
                            "segment_index": segment_index,
                            "speaker_original": speaker,
                            "speaker_zh_cn": "",
                            "voice": voices,
                            "display_prefix": prefix,
                            "original_text": text,
                            "translation_zh_cn": "",
                            "translator_note": "",
                        }
                    )
        files.append({"file": source.name, "text_entries": file_entries})

    table = localization_root / "scenario_dialogue_zh_cn.tsv"
    with table.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return rows, files, text_entries


def main():
    parser = argparse.ArgumentParser(description="生成汉化文本工作区")
    parser.add_argument("extracted", type=pathlib.Path)
    parser.add_argument("localization", type=pathlib.Path)
    args = parser.parse_args()

    extracted_root = args.extracted.resolve()
    localization_root = args.localization.resolve()
    localization_root.mkdir(parents=True, exist_ok=True)

    inventory, converted, skipped = write_utf8_copies(
        extracted_root, localization_root
    )
    dialogue_rows, scenario_files, text_entries = build_scenario_table(
        extracted_root, localization_root
    )
    tjs_decompiled = list((localization_root / "tjs_decompiled").rglob("*.tjs"))
    summary = {
        "text_source_files": len(inventory),
        "text_files_converted_to_utf8": converted,
        "text_files_skipped": skipped,
        "tjs2100_decompiled_files": len(tjs_decompiled),
        "scenario_files": scenario_files,
        "scenario_text_entries": text_entries,
        "scenario_dialogue_segments": len(dialogue_rows),
        "translation_table": "scenario_dialogue_zh_cn.tsv",
        "text_inventory": "text_inventory.csv",
    }
    with (localization_root / "_localization_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
