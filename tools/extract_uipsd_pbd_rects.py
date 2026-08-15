from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "savedata" / "krkr.console.log"
OUTPUT_PATH = ROOT / "build" / "uipsd_localize" / "pbd_state_rectangles.json"


def balanced_square(text: str, open_index: int) -> str:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[open_index : index + 1]
    raise ValueError(f"unbalanced array starting at {open_index}")


def int_field(payload: str, key: str) -> int | None:
    match = re.search(rf'"{re.escape(key)}",(-?\d+)', payload)
    return int(match.group(1)) if match else None


def str_field(payload: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}","([^"]*)"', payload)
    return match.group(1) if match else None


def pbd_payloads() -> dict[str, str]:
    lines = LOG_PATH.read_text(encoding="utf-16").splitlines()
    payloads: dict[str, str] = {}
    for index, line in enumerate(lines):
        marker = "UIPBD_FILE_BEGIN="
        if marker not in line or index + 1 >= len(lines):
            continue
        file_name = line.split(marker, 1)[1].strip()
        candidate = lines[index + 1]
        if len(candidate) > len(payloads.get(file_name, "")):
            payloads[file_name] = candidate
    return payloads


def extract_records(file_name: str, payload: str) -> list[dict]:
    result_marker = '"result",%['
    result_at = payload.rfind(result_marker)
    if result_at < 0:
        return []
    result_open = payload.find("[", result_at)
    result = balanced_square(payload, result_open)

    records: list[dict] = []
    pattern = re.compile(r'(?:^|[\[,])"([^"]+)",%\["width",')
    for match in pattern.finditer(result):
        semantic_key = match.group(1)
        record_open = result.find("%[", match.start()) + 1
        record = balanced_square(result, record_open)
        uiname = str_field(record, "uiname") or semantic_key
        semantic_name = str_field(record, "name") or semantic_key
        logical_width = int_field(record, "width")
        logical_height = int_field(record, "height")

        states: list[dict] = []
        state_pattern = re.compile(r'(?:^|[\[,])"([^"]+)",%\["w",')
        for state_match in state_pattern.finditer(record):
            state_name = state_match.group(1)
            state_open = record.find("%[", state_match.start()) + 1
            state = balanced_square(record, state_open)
            storage = str_field(state, "storage")
            cx = int_field(state, "cx")
            cy = int_field(state, "cy")
            cw = int_field(state, "cw")
            ch = int_field(state, "ch")
            if not storage or None in (cx, cy, cw, ch):
                continue
            states.append(
                {
                    "state": state_name,
                    "storage": storage,
                    "x": cx,
                    "y": cy,
                    "width": cw,
                    "height": ch,
                    "rotated": bool(int_field(state, "cr") or 0),
                    "logical_width": int_field(state, "w"),
                    "logical_height": int_field(state, "h"),
                    "offset_x": int_field(state, "ox"),
                    "offset_y": int_field(state, "oy"),
                }
            )
        if states:
            records.append(
                {
                    "pbd_file": file_name,
                    "key": semantic_key,
                    "uiname": uiname,
                    "name": semantic_name,
                    "logical_width": logical_width,
                    "logical_height": logical_height,
                    "states": states,
                }
            )
    return records


def main() -> None:
    payloads = pbd_payloads()
    records: list[dict] = []
    for file_name, payload in sorted(payloads.items()):
        records.extend(extract_records(file_name, payload))

    result = {
        "source_log": str(LOG_PATH),
        "pbd_file_count": len(payloads),
        "record_count": len(records),
        "state_count": sum(len(item["states"]) for item in records),
        "records": records,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    storages = sorted(
        {state["storage"] for item in records for state in item["states"]}
    )
    print(
        f"pbd_files={len(payloads)} records={len(records)} "
        f"states={result['state_count']} storages={len(storages)}"
    )
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
