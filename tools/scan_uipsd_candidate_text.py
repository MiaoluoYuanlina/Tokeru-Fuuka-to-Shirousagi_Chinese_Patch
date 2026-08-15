from __future__ import annotations

import sys
from pathlib import Path

import scan_uipsd_text as scanner


ROOT = Path(__file__).resolve().parents[1]
scanner.SOURCE_DIR = ROOT / "build" / "uipsd_localize" / "candidate_png"
scanner.OUTPUT_DIR = ROOT / "build" / "uipsd_localize" / "candidate_ocr"
requested = set(sys.argv[1:])
scanner.CANDIDATES = [
    name
    for name in scanner.CANDIDATES
    if (scanner.SOURCE_DIR / name).is_file() and (not requested or name in requested)
]
scanner.main([])
