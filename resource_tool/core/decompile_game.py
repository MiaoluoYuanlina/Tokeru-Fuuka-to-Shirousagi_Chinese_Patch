from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
PYTHON = ROOT / "runtime" / "python" / "python.exe"
NODE = ROOT / "runtime" / "node" / "bin" / "node.exe"
FREEMOTE = CORE / "FreeMote-v4.7.0"
USABLE_MANIFEST_STATUSES = {"verified", "unverified_no_adler32"}


def run(args: list[str], cwd: Path) -> None:
    print("  >", " ".join(f'\"{x}\"' if " " in x else x for x in args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def merge_archives(archive_outputs: list[tuple[Path, Path]], extracted: Path) -> int:
    selected: dict[str, tuple[dict[str, str], Path, str]] = {}
    for archive, folder in archive_outputs:
        manifest = folder / "_xp3_manifest.csv"
        with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                # A zero Adler32 in the source archive means the payload can
                # only be verified by its declared length.  extract_xp3 has
                # already checked that length, so the resource is usable and
                # must not be dropped from the merged working tree.
                if row.get("status") not in USABLE_MANIFEST_STATUSES:
                    continue
                source = folder / PurePosixPath(row["extracted_path"])
                if source.is_file():
                    selected[row["archive_name"].casefold()] = (row, source, archive.name)

    extracted.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for index, (_, (row, source, archive_name)) in enumerate(sorted(selected.items()), start=1):
        relative = PurePosixPath(row["archive_name"])
        if any(part in ("", ".", "..") for part in relative.parts):
            continue
        destination = extracted / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        merged = dict(row)
        merged["index"] = str(index)
        merged["extracted_path"] = relative.as_posix()
        merged["source_archive"] = archive_name
        rows.append(merged)

    fields = list(rows[0].keys()) if rows else []
    with (extracted / "_xp3_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (extracted / "_xp3_summary.json").write_text(
        json.dumps({"files_total": len(rows), "files_verified": len(rows), "files_failed": 0}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and decompile Kazeshiro game resources")
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    exe = args.exe.resolve()
    output = args.output.resolve()
    if not exe.is_file() or exe.suffix.lower() != ".exe":
        raise FileNotFoundError(f"游戏主程序不存在：{exe}")
    game = exe.parent
    archives = sorted(game.glob("*.xp3"), key=lambda p: (p.name.lower() == "patch.xp3", p.name.lower()))
    if not archives:
        raise FileNotFoundError(f"游戏目录没有 XP3 资源包：{game}")
    output.mkdir(parents=True, exist_ok=True)
    extracted_archives = output / "extracted_archives"
    extracted = output / "extracted"
    localization = output / "localization"
    archive_outputs: list[tuple[Path, Path]] = []

    print(f"发现 {len(archives)} 个 XP3 资源包。", flush=True)
    for archive in archives:
        target = extracted_archives / archive.stem
        target.mkdir(parents=True, exist_ok=True)
        run([str(PYTHON), str(CORE / "extract_xp3.py"), str(archive), str(target)], output)
        archive_outputs.append((archive, target))
    merged_count = merge_archives(archive_outputs, extracted)
    print(f"合并后资源文件：{merged_count}", flush=True)

    scenario_out = extracted / "_scenario_decompiled"
    scenario_out.mkdir(parents=True, exist_ok=True)
    scns = sorted(extracted.rglob("*.scn"))
    for path in scns:
        run([str(FREEMOTE / "PsbDecompile.exe"), "-t", "Scn", "-o", str(scenario_out), str(path)], output)

    tlgs = sorted(extracted.rglob("*.tlg"))
    if tlgs:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            raise FileNotFoundError("未找到 Windows PowerShell，无法生成 TLG PNG 预览")
        run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CORE / "convert_all_tlg.ps1"), "-Extracted", str(extracted), "-TlgLibrary", str(FREEMOTE / "lib" / "TlgLib.dll")], output)

    tjs_out = localization / "tjs_decompiled"
    tjs_out.mkdir(parents=True, exist_ok=True)
    run([str(PYTHON), str(CORE / "tjs2-decompiler" / "tjs2_decompiler.py"), str(extracted), "-o", str(tjs_out), "-r", "-e", "utf-8"], output)
    run([str(PYTHON), str(CORE / "build_localization_workspace.py"), str(extracted), str(localization)], output)
    table = localization / "scenario_dialogue_zh_cn.tsv"
    xlsx = localization / "scenario_dialogue_zh_cn.xlsx"
    run([str(NODE), str(CORE / "build_scenario_workbook.mjs"), "--tsv", str(table), "--output", str(xlsx)], output)

    (output / "source_game.json").write_text(json.dumps({"exe": str(exe), "game_directory": str(game), "archives": [str(x) for x in archives]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WORK_ROOT={output}")
    print(f"SCENARIO_TABLE={xlsx}")


if __name__ == "__main__":
    main()
