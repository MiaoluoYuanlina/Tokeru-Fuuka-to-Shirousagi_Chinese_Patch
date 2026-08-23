from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output_dir.resolve()
    if source.is_file():
        source_dir = source.parent
        files = [source.name]
    elif source.is_dir():
        source_dir = source
        extensions = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        files = [p.relative_to(source_dir).as_posix() for p in sorted(source_dir.rglob("*")) if p.is_file() and p.suffix.lower() in extensions]
    else:
        raise FileNotFoundError(f"图片或文件夹不存在：{source}")
    if not files:
        raise FileNotFoundError("没有找到支持的图片")

    tool_path = Path(__file__).with_name("scan_uipsd_text.py")
    spec = importlib.util.spec_from_file_location("generic_scan_engine", tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 OCR 引擎")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scan_args = ["--source-dir", str(source_dir), "--output-dir", str(output)]
    for file_name in files:
        scan_args += ["--files", file_name]
    module.main(scan_args)

    result_path = output / "ocr_results.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    for result in payload.get("results", []):
        relative = Path(result["file_name"])
        result["relative_path"] = relative.as_posix()
        result["source_path"] = str((source_dir / relative).resolve())
    payload["selected_input"] = str(source)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

