from __future__ import annotations

from pathlib import Path

from create_uipsd_scan_workspace import build_sheets


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "build" / "uipsd_localize" / "candidate_png"
OUTPUT = ROOT / "build" / "uipsd_localize" / "qa_contact_sheets"
OUTPUT.mkdir(parents=True, exist_ok=True)

paths = sorted(SOURCE.glob("*.png"), key=lambda item: item.name.casefold())
pack_paths = [path for path in paths if "__pack" in path.stem]
background_paths = [path for path in paths if path not in pack_paths]
outputs = build_sheets(pack_paths, OUTPUT, "pack", 2, 4, 900, 600)
outputs += build_sheets(background_paths, OUTPUT, "background", 1, 2, 1400, 800)
print(f"files={len(paths)} sheets={len(outputs)}")
for output in outputs:
    print(output)
