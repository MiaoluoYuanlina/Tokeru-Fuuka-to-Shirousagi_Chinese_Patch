from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_DATA = ROOT / "build" / "uipsd_scan" / "workbook_data.json"
TRANSLATIONS = ROOT / "build" / "uipsd_localize" / "translations_from_excel.json"
OUTPUT = ROOT / "build" / "uipsd_localize" / "translation_position_report.txt"


def main() -> None:
    workbook = json.loads(WORKBOOK_DATA.read_text(encoding="utf-8"))
    completed = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    chinese_by_id = {
        row["id"]: row["chinese_translation"]
        for row in completed["rows"]
    }
    # Safe rendering-only punctuation correction. The user's workbook remains untouched.
    chinese_by_id["UI-0001"] = "如果不需要此功能，请选择“OFF”。"

    by_file: dict[str, list[dict]] = defaultdict(list)
    for row in workbook["translations"]:
        enriched = dict(row)
        enriched["chinese_translation"] = chinese_by_id.get(row["id"], "")
        by_file[row["file_name"]].append(enriched)

    lines: list[str] = []
    for file_name in sorted(by_file):
        rows = by_file[file_name]
        lines.append(f"## {file_name} ({len(rows)})")
        for row in rows:
            rect = f"{row.get('x')},{row.get('y')} {row.get('width')}x{row.get('height')}"
            lines.append(
                f"{row['id']} [{rect}] variants={row.get('variant_count', 1)} "
                f"{row['original_text']} -> {row['chinese_translation']}"
            )
        lines.append("")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"files={len(by_file)} positions={sum(map(len, by_file.values()))}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
