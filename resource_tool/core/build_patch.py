#!/usr/bin/env python3
"""Build a repeatable Kirikiri patch.xp3 from a selected translation TSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import time
import zlib


XP3_MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"
USABLE_MANIFEST_STATUSES = {"verified", "unverified_no_adler32"}
EXPECTED_COLUMNS = [
    "source_file",
    "scene_index",
    "scene_label",
    "text_index",
    "segment_index",
    "speaker_original",
    "speaker_zh_cn",
    "voice",
    "display_prefix",
    "original_text",
    "translation_zh_cn",
    "translator_note",
]
GBK_HELP_TEXT_PATHS = (
    "main/help_sys.txt",
    "main/help_file.txt",
    "main/help_exch.txt",
    "main/help_mes.txt",
)


def normalized(value: str | None) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n")


def run(command: list[str], cwd: pathlib.Path) -> None:
    print("  >", " ".join(f'"{item}"' if " " in item else item for item in command))
    subprocess.run(command, cwd=cwd, check=True)


def read_translation_rows(tsv_path: pathlib.Path) -> list[dict[str, str]]:
    with tsv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "TSV 列结构不正确。\n"
                f"期望: {EXPECTED_COLUMNS}\n"
                f"实际: {reader.fieldnames}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError("TSV 中没有剧情数据")
    return rows


def update_scenario_jsons(
    rows: list[dict[str, str]], source_dir: pathlib.Path, work_dir: pathlib.Path
) -> tuple[dict[str, pathlib.Path], dict[str, dict], int, int]:
    documents: dict[str, dict] = {}
    output_jsons: dict[str, pathlib.Path] = {}
    translated = 0
    translated_speakers = 0
    seen_keys: set[tuple[str, int, int, int]] = set()

    for row_number, row in enumerate(rows, 2):
        source_file = row["source_file"]
        try:
            scene_index = int(row["scene_index"])
            text_index = int(row["text_index"])
            segment_index = int(row["segment_index"])
        except ValueError as exc:
            raise ValueError(f"TSV 第 {row_number} 行的索引不是整数") from exc
        key = (source_file, scene_index, text_index, segment_index)
        if key in seen_keys:
            raise ValueError(f"TSV 第 {row_number} 行重复定位: {key}")
        seen_keys.add(key)

        if source_file not in documents:
            source_json = source_dir / source_file
            if not source_json.is_file():
                raise FileNotFoundError(f"找不到剧情 JSON: {source_json}")
            documents[source_file] = json.loads(source_json.read_text(encoding="utf-8"))

        document = documents[source_file]
        try:
            scene = document["scenes"][scene_index]
            text_entry = scene["texts"][text_index]
            segment = text_entry[1][segment_index]
        except (IndexError, KeyError, TypeError) as exc:
            raise ValueError(f"TSV 第 {row_number} 行无法定位到剧情数据: {key}") from exc

        if normalized(scene.get("label", "")) != normalized(row["scene_label"]):
            raise ValueError(f"TSV 第 {row_number} 行 scene_label 与原始剧情不一致")
        original_speaker = "" if text_entry[0] is None else str(text_entry[0])
        if normalized(original_speaker) != normalized(row["speaker_original"]):
            raise ValueError(f"TSV 第 {row_number} 行角色名与原始剧情不一致")
        original_text = "" if segment[1] is None else str(segment[1])
        if normalized(original_text) != normalized(row["original_text"]):
            raise ValueError(f"TSV 第 {row_number} 行原文与剧情 JSON 不一致")

        translation = normalized(row["translation_zh_cn"])
        target_text = translation if translation.strip() else original_text
        speaker_translation = normalized(row["speaker_zh_cn"])
        if speaker_translation.strip():
            text_entry[0] = speaker_translation
            translated_speakers += 1
        if translation.strip():
            translated += 1

        segment[1] = target_text
        plain_text = target_text.replace("\\n", "")
        if len(segment) >= 3 and isinstance(segment[2], int):
            segment[2] = len(plain_text)
        if len(segment) >= 4 and isinstance(segment[3], str):
            segment[3] = plain_text
        if len(segment) >= 5 and isinstance(segment[4], str):
            segment[4] = plain_text

    expected_files = sorted(path.name for path in source_dir.glob("*.txt.json"))
    if sorted(documents) != expected_files:
        raise ValueError(
            "TSV 未覆盖全部剧情文件。\n"
            f"期望: {expected_files}\n实际: {sorted(documents)}"
        )
    expected_keys: set[tuple[str, int, int, int]] = set()
    for source_file in expected_files:
        document = documents[source_file]
        for scene_index, scene in enumerate(document.get("scenes", [])):
            for text_index, entry in enumerate(scene.get("texts", [])):
                segments = entry[1] if isinstance(entry, list) and len(entry) > 1 else []
                for segment_index, segment in enumerate(segments):
                    if isinstance(segment, list) and len(segment) > 1 and isinstance(segment[1], str):
                        expected_keys.add((source_file, scene_index, text_index, segment_index))
    if seen_keys != expected_keys:
        missing = sorted(expected_keys - seen_keys)[:10]
        extra = sorted(seen_keys - expected_keys)[:10]
        raise ValueError(
            "TSV 剧情定位不完整或包含多余行。\n"
            f"缺少示例: {missing}\n多余示例: {extra}"
        )

    json_dir = work_dir / "scenario_json"
    json_dir.mkdir(parents=True, exist_ok=True)
    for source_file, document in documents.items():
        output_json = json_dir / source_file
        output_json.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        resx_source = source_dir / source_file.replace(".json", ".resx.json")
        if not resx_source.is_file():
            raise FileNotFoundError(f"找不到 FreeMote 元数据: {resx_source}")
        shutil.copy2(resx_source, json_dir / resx_source.name)
        output_jsons[source_file] = output_json
    return output_jsons, documents, translated, translated_speakers


def compile_scenarios(
    project_root: pathlib.Path,
    output_jsons: dict[str, pathlib.Path],
    work_dir: pathlib.Path,
    tools_root: pathlib.Path | None = None,
) -> dict[str, pathlib.Path]:
    tools_root = tools_root or (project_root / "tools")
    psbuild = tools_root / "FreeMote-v4.7.0" / "PsBuild.exe"
    decompiler = tools_root / "FreeMote-v4.7.0" / "PsbDecompile.exe"
    if not psbuild.is_file() or not decompiler.is_file():
        raise FileNotFoundError("找不到 FreeMote，请确认 tools/FreeMote-v4.7.0 完整存在")

    scn_dir = work_dir / "scn"
    check_dir = work_dir / "scenario_check"
    scn_dir.mkdir(parents=True, exist_ok=True)
    check_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, pathlib.Path] = {}
    for source_file, json_path in sorted(output_jsons.items()):
        # Initialize.tjs mounts patch.xp3 only at its root.  This engine does
        # not recursively add subdirectories from that archive to AutoPath,
        # so override entries must use the same flat basenames the game opens.
        archive_name = source_file.removesuffix(".json") + ".scn"
        scn_path = scn_dir / archive_name
        run([str(psbuild), "-o", str(scn_path), str(json_path)], project_root)
        original_scn = project_root / "extracted" / "scn" / archive_name
        expected_magic = (
            original_scn.read_bytes()[:4] if original_scn.is_file() else None
        )
        actual_magic = scn_path.read_bytes()[:4] if scn_path.is_file() else b""
        valid_magic = (
            actual_magic == expected_magic
            if expected_magic is not None
            else actual_magic in (b"mdf\x00", b"PSB\x00")
        )
        if not scn_path.is_file() or not valid_magic:
            raise ValueError(f"SCN 回编译失败或格式错误: {scn_path}")
        run(
            [str(decompiler), "-t", "Scn", "-o", str(check_dir), str(scn_path)],
            project_root,
        )
        results[archive_name] = scn_path
    return results


def verify_compiled_scenarios(
    rows: list[dict[str, str]], check_dir: pathlib.Path
) -> None:
    documents: dict[str, dict] = {}
    for row_number, row in enumerate(rows, 2):
        source_file = row["source_file"]
        if source_file not in documents:
            check_json = check_dir / source_file
            if not check_json.is_file():
                raise FileNotFoundError(f"找不到回编译验证 JSON: {check_json}")
            documents[source_file] = json.loads(check_json.read_text(encoding="utf-8"))
        document = documents[source_file]
        scene_index = int(row["scene_index"])
        text_index = int(row["text_index"])
        segment_index = int(row["segment_index"])
        entry = document["scenes"][scene_index]["texts"][text_index]
        actual_text = normalized(entry[1][segment_index][1])
        translation = normalized(row["translation_zh_cn"])
        expected_text = translation if translation.strip() else normalized(row["original_text"])
        if actual_text != expected_text:
            raise ValueError(f"SCN 验证失败：第 {row_number} 行译文不一致")
        speaker_translation = normalized(row["speaker_zh_cn"])
        expected_speaker = speaker_translation if speaker_translation.strip() else normalized(row["speaker_original"])
        actual_speaker = "" if entry[0] is None else normalized(str(entry[0]))
        if actual_speaker != expected_speaker:
            raise ValueError(f"SCN 验证失败：第 {row_number} 行角色名不一致")


def detect_modified_resources(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    extracted = project_root / "extracted"
    manifest = extracted / "_xp3_manifest.csv"
    extracted_archives = project_root / "extracted_archives"
    resources: dict[str, pathlib.Path] = {}

    def add_flat_resource(original_name: str, source_path: pathlib.Path) -> None:
        archive_name = pathlib.PurePosixPath(original_name.replace("\\", "/")).name
        if not archive_name or archive_name in (".", ".."):
            raise ValueError(f"补丁资源文件名非法: {original_name}")
        collision = next(
            (name for name in resources if name.casefold() == archive_name.casefold()),
            None,
        )
        if collision is not None and resources[collision] != source_path:
            previous_path = resources[collision]
            if previous_path.read_bytes() == source_path.read_bytes():
                return
            raise ValueError(
                f"扁平补丁中出现同名且内容不同的修改资源: {collision}\n"
                f"  {previous_path}\n  {source_path}\n"
                "请只保留其中一份修改，或使两份文件内容一致。"
            )
        resources[archive_name] = source_path

    def collect_manifest_changes(source_root: pathlib.Path) -> None:
        source_manifest = source_root / "_xp3_manifest.csv"
        if not source_manifest.is_file():
            return
        with source_manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") not in USABLE_MANIFEST_STATUSES:
                    continue
                path = source_root / pathlib.PurePosixPath(row["extracted_path"])
                if not path.is_file():
                    continue
                data = path.read_bytes()
                checksum = zlib.adler32(data) & 0xFFFFFFFF
                if (
                    len(data) == int(row["size"])
                    and checksum == int(row["actual_adler32"], 16)
                ):
                    continue
                archive_name = row["archive_name"]
                if archive_name.lower().startswith("scn/") and archive_name.lower().endswith(".scn"):
                    continue
                add_flat_resource(archive_name, path)

    if not manifest.is_file():
        raise FileNotFoundError(f"找不到合并资源清单: {manifest}")
    collect_manifest_changes(extracted)

    # Large formal-edition archives (for example evimage.xp3) are extracted
    # into separate folders and may not be copied into the merged `extracted`
    # tree.  Compare every per-archive manifest as well so edits made in
    # extracted_archives/<archive>/ are not silently omitted from patch.xp3.
    if extracted_archives.is_dir():
        for archive_root in sorted(
            (path for path in extracted_archives.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            collect_manifest_changes(archive_root)

    extra_root = project_root / "patch_assets"
    if extra_root.is_dir():
        for path in sorted(extra_root.rglob("*")):
            if not path.is_file() or path.name.upper() == "README.TXT":
                continue
            archive_name = path.relative_to(extra_root).as_posix()
            if any(part in ("", ".", "..") for part in pathlib.PurePosixPath(archive_name).parts):
                raise ValueError(f"patch_assets 中存在非法路径: {archive_name}")
            add_flat_resource(archive_name, path)
    return resources


def convert_modified_tlg_previews(
    project_root: pathlib.Path,
    work_dir: pathlib.Path,
    tools_root: pathlib.Path | None = None,
) -> dict[str, pathlib.Path]:
    tools_root = tools_root or (project_root / "tools")
    converter = tools_root / "convert_modified_tlg_previews.ps1"
    if not converter.is_file():
        raise FileNotFoundError(f"找不到 TLG 预览转换脚本: {converter}")
    output_root = work_dir / "tlg_previews"
    report_path = work_dir / "tlg_preview_report.json"
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise FileNotFoundError("找不到 Windows PowerShell，无法转换 TLG 预览")
    run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(converter),
            "-ProjectRoot",
            str(project_root),
            "-ToolRoot",
            str(tools_root),
            "-OutputRoot",
            str(output_root),
            "-ReportPath",
            str(report_path),
        ],
        project_root,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results: dict[str, pathlib.Path] = {}
    for entry in report["entries"]:
        original_name = entry["archive_name"]
        archive_name = pathlib.PurePosixPath(original_name).name
        output_path = pathlib.Path(entry["output_path"])
        if not output_path.is_file():
            raise FileNotFoundError(f"转换后的 TLG 不存在: {output_path}")
        collision = next(
            (name for name in results if name.casefold() == archive_name.casefold()),
            None,
        )
        if collision is not None:
            raise ValueError(f"修改过的 TLG 预览出现扁平文件名冲突: {collision} / {archive_name}")
        results[archive_name] = output_path
    return results


def collect_utf8_text_resources(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Collect the UTF-8 text mirror while excluding extractor metadata."""
    source_root = project_root / "localization" / "text_utf8"
    if not source_root.is_dir():
        raise FileNotFoundError(f"找不到 UTF-8 文本目录: {source_root}")

    resources: dict[str, pathlib.Path] = {}
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if relative.name == "_xp3_manifest.csv" or relative.parts[0] == "_long_names":
            continue
        archive_name = relative.as_posix()
        folded = archive_name.casefold()
        collision = next((name for name in resources if name.casefold() == folded), None)
        if collision is not None:
            raise ValueError(f"UTF-8 文本中存在大小写重名: {collision} / {archive_name}")
        resources[archive_name] = path

    required = ("AppConfig.tjs", "main/Storages.tjs", "main/default.tjs")
    missing = [name for name in required if name not in resources]
    if missing:
        raise FileNotFoundError(f"UTF-8 文本目录不完整，缺少: {missing}")
    return resources


def convert_system_text_to_utf16(
    project_root: pathlib.Path, work_dir: pathlib.Path
) -> dict[str, pathlib.Path]:
    """Convert the UTF-8 mirror to BOM-marked UTF-16LE for locale-independent loading."""
    source_resources = collect_utf8_text_resources(project_root)
    output_root = work_dir / "system_text_utf16le"
    resources: dict[str, pathlib.Path] = {}
    for archive_name, source_path in source_resources.items():
        text = source_path.read_text(encoding="utf-8-sig")
        output_path = output_root / pathlib.PurePosixPath(archive_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\xff\xfe" + text.encode("utf-16le"))
        resources[archive_name] = output_path
    return resources


def convert_help_text_to_gbk(
    project_root: pathlib.Path, work_dir: pathlib.Path
) -> dict[str, pathlib.Path]:
    """Prepare custom UI help files for parsers that always use the Windows ACP."""
    source_root = project_root / "localization" / "text_utf8"
    output_root = work_dir / "help_text_gbk"
    replacements = {
        "・": "·",
        "⇒": "=>",
    }
    resources: dict[str, pathlib.Path] = {}
    for source_name in GBK_HELP_TEXT_PATHS:
        source_path = source_root / pathlib.PurePosixPath(source_name)
        if not source_path.is_file():
            raise FileNotFoundError(f"找不到 UI 帮助文本: {source_path}")
        text = source_path.read_text(encoding="utf-8-sig")
        for original, replacement in replacements.items():
            text = text.replace(original, replacement)
        try:
            encoded = text.encode("gbk")
        except UnicodeEncodeError as exc:
            problem = text[exc.start : exc.end]
            raise ValueError(
                f"UI 帮助文本包含 GBK 无法表示的字符: {source_name} {problem!r}"
            ) from exc
        # HelpTextLoader calls Array.load("help_*.txt") with a root-level
        # storage name.  Keeping the original main/ prefix in a separate XP3
        # does not override the file found through the game's auto path.
        archive_name = pathlib.PurePosixPath(source_name).name
        output_path = output_root / archive_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(encoded)
        resources[archive_name] = output_path
    return resources


def merge_patch_entries(
    groups: list[tuple[str, dict[str, pathlib.Path]]],
) -> dict[str, pathlib.Path]:
    entries: dict[str, pathlib.Path] = {}
    names_by_casefold: dict[str, tuple[str, str]] = {}
    for group_name, group in groups:
        for archive_name, source_path in group.items():
            folded = archive_name.casefold()
            if folded in names_by_casefold:
                other_name, other_group = names_by_casefold[folded]
                raise ValueError(
                    f"补丁条目重名: {other_name}（{other_group}）与 "
                    f"{archive_name}（{group_name}）"
                )
            names_by_casefold[folded] = (archive_name, group_name)
            entries[archive_name] = source_path
    return entries


def chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("<Q", len(payload)) + payload


def create_xp3(entries: dict[str, pathlib.Path], output_path: pathlib.Path) -> list[dict]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    index_records: list[bytes] = []
    report_entries: list[dict] = []
    with temporary.open("wb") as archive:
        archive.write(XP3_MAGIC)
        archive.write(b"\x00" * 8)
        for archive_name, source_path in sorted(entries.items()):
            data = source_path.read_bytes()
            compressed = zlib.compress(data, 9)
            use_compressed = len(compressed) + 16 < len(data)
            stored = compressed if use_compressed else data
            segment_flags = 1 if use_compressed else 0
            offset = archive.tell()
            archive.write(stored)

            name_data = archive_name.encode("utf-16le")
            info = struct.pack(
                "<IQQH", 0, len(data), len(stored), len(name_data) // 2
            ) + name_data
            segment = struct.pack(
                "<IQQQ", segment_flags, offset, len(data), len(stored)
            )
            adler = zlib.adler32(data) & 0xFFFFFFFF
            file_payload = (
                chunk(b"info", info)
                + chunk(b"segm", segment)
                + chunk(b"adlr", struct.pack("<I", adler))
            )
            index_records.append(chunk(b"File", file_payload))
            report_entries.append(
                {
                    "archive_name": archive_name,
                    "source": str(source_path),
                    "original_size": len(data),
                    "stored_size": len(stored),
                    "adler32": f"{adler:08x}",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )

        index_offset = archive.tell()
        raw_index = b"".join(index_records)
        packed_index = zlib.compress(raw_index, 9)
        archive.write(b"\x01")
        archive.write(struct.pack("<QQ", len(packed_index), len(raw_index)))
        archive.write(packed_index)
        archive.seek(len(XP3_MAGIC))
        archive.write(struct.pack("<Q", index_offset))
    os.replace(temporary, output_path)
    return report_entries


def verify_patch(
    python_exe: pathlib.Path,
    project_root: pathlib.Path,
    patch_path: pathlib.Path,
    work_dir: pathlib.Path,
    expected_entries: int,
    tools_root: pathlib.Path | None = None,
) -> None:
    tools_root = tools_root or (project_root / "tools")
    verify_dir = work_dir / "xp3_verify"
    run(
        [
            str(python_exe),
            str(tools_root / "extract_xp3.py"),
            str(patch_path),
            str(verify_dir),
        ],
        project_root,
    )
    summary = json.loads((verify_dir / "_xp3_summary.json").read_text(encoding="utf-8"))
    if summary["files_total"] != expected_entries or summary["files_failed"] != 0:
        raise ValueError(f"patch.xp3 最终验证失败: {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 kazeshiro_demo 汉化补丁")
    parser.add_argument("--project-root", required=True, type=pathlib.Path)
    parser.add_argument("--tsv", required=True, type=pathlib.Path)
    parser.add_argument(
        "--tools-root",
        type=pathlib.Path,
        help="工具目录；省略时使用游戏工作目录下的 tools",
    )
    system_text_group = parser.add_mutually_exclusive_group()
    system_text_group.add_argument(
        "--skip-utf8-system-text",
        action="store_true",
        help="不把 localization/text_utf8 中的系统文本加入补丁",
    )
    system_text_group.add_argument(
        "--unicode-system-text",
        action="store_true",
        help="把系统文本转换成带 BOM 的 UTF-16LE，避免受 Windows 区域代码页影响",
    )
    parser.add_argument(
        "--gbk-help-text",
        action="store_true",
        help="把四个 UI 帮助文本转换为中文 Windows 自定义解析器需要的 GBK",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    tsv_path = args.tsv.resolve()
    tools_root = (
        args.tools_root.resolve()
        if args.tools_root is not None
        else (project_root / "tools").resolve()
    )
    if not tsv_path.is_file():
        raise FileNotFoundError(f"TSV 不存在: {tsv_path}")
    if args.gbk_help_text and not args.skip_utf8_system_text:
        raise ValueError("--gbk-help-text 必须和 --skip-utf8-system-text 一起使用")
    work_dir = (project_root / "build" / "patch_work").resolve()
    expected_work_dir = (project_root / "build" / "patch_work").resolve()
    if work_dir != expected_work_dir or project_root not in work_dir.parents:
        raise ValueError("临时构建目录校验失败")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    print("[1/8] 读取并验证翻译 TSV")
    rows = read_translation_rows(tsv_path)
    print(f"  剧情行数: {len(rows)}")

    print("[2/8] 回填剧情 JSON")
    output_jsons, _, translated, translated_speakers = update_scenario_jsons(
        rows, project_root / "extracted" / "_scenario_decompiled", work_dir
    )
    print(f"  已填写译文: {translated}/{len(rows)}")
    print(f"  已填写中文角色名: {translated_speakers}/{len(rows)}")

    print("[3/8] 回编译并复核 5 个 SCN")
    scenarios = compile_scenarios(project_root, output_jsons, work_dir, tools_root)
    verify_compiled_scenarios(rows, work_dir / "scenario_check")
    print("  SCN 文本逐行复核通过")

    print("[4/8] 收集修改过的图片和其他资源")
    resources = detect_modified_resources(project_root)
    for archive_name in sorted(resources):
        print(f"  修改资源: {archive_name}")

    print("[5/8] 检测并转换修改过的 TLG 预览")
    tlg_resources = convert_modified_tlg_previews(project_root, work_dir, tools_root)
    for archive_name in sorted(tlg_resources):
        print(f"  修改 TLG: {archive_name}")

    system_text_encoding = None
    if args.unicode_system_text:
        print("[6/8] 将系统文本转换为 UTF-16LE BOM（跨区域安全模式）")
        utf8_text_resources = convert_system_text_to_utf16(project_root, work_dir)
        system_text_encoding = "utf-16le-bom"
        print(f"  Unicode 系统文本: {len(utf8_text_resources)} 个")
    elif args.skip_utf8_system_text:
        print("[6/8] 跳过系统文本")
        utf8_text_resources: dict[str, pathlib.Path] = {}
    else:
        print("[6/8] 收集 UTF-8 系统文本")
        utf8_text_resources = collect_utf8_text_resources(project_root)
        print(f"  UTF-8 文本: {len(utf8_text_resources)} 个")
    if args.gbk_help_text:
        gbk_help_resources = convert_help_text_to_gbk(project_root, work_dir)
        print(f"  GBK UI 帮助文本: {len(gbk_help_resources)} 个")
        # The editable UTF-8 help sources are converted to root-level GBK
        # entries above.  If an extracted main/help_*.txt file was edited as
        # well, detect_modified_resources() reports the same flattened archive
        # name.  The dedicated conversion is authoritative in GBK mode, so do
        # not feed both copies to merge_patch_entries().
        gbk_names = {name.casefold() for name in gbk_help_resources}
        overridden_help = [
            name for name in resources if name.casefold() in gbk_names
        ]
        for name in overridden_help:
            del resources[name]
        if overridden_help:
            print(
                "  GBK 帮助文本覆盖同名修改资源: "
                + ", ".join(sorted(overridden_help))
            )
    else:
        gbk_help_resources: dict[str, pathlib.Path] = {}
    entries = merge_patch_entries(
        [
            ("UTF-8 文本", utf8_text_resources),
            ("GBK UI 帮助文本", gbk_help_resources),
            ("修改资源", resources),
            ("修改 TLG", tlg_resources),
            ("剧情", scenarios),
        ]
    )

    print("[7/8] 生成 patch.xp3")
    patch_path = project_root / "patch.xp3"
    report_entries = create_xp3(entries, patch_path)

    print("[8/8] 重新解包验证 patch.xp3")
    verify_patch(
        pathlib.Path(sys.executable),
        project_root,
        patch_path,
        work_dir,
        len(entries),
        tools_root,
    )

    report = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "translation_tsv": str(tsv_path),
        "tools_root": str(tools_root),
        "translation_rows": len(rows),
        "translated_rows": translated,
        "translated_speaker_rows": translated_speakers,
        "scenario_files": len(scenarios),
        "modified_resource_files": len(resources),
        "modified_tlg_files": len(tlg_resources),
        "utf8_text_files": len(utf8_text_resources),
        "system_text_files": len(utf8_text_resources),
        "gbk_help_text_files": len(gbk_help_resources),
        "skipped_utf8_system_text": args.skip_utf8_system_text,
        "system_text_encoding": system_text_encoding,
        "patch_entries": len(entries),
        "patch_path": str(patch_path),
        "patch_size": patch_path.stat().st_size,
        "entries": report_entries,
    }
    (project_root / "build" / "patch_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\n构建成功！")
    print(f"补丁: {patch_path}")
    print(f"大小: {patch_path.stat().st_size:,} 字节")
    print(
        f"内容: {len(entries)} 个文件（{len(scenarios)} 个剧情 + "
        f"{len(resources)} 个修改资源 + {len(tlg_resources)} 个 TLG + "
        f"{len(utf8_text_resources)} 个系统文本 + "
        f"{len(gbk_help_resources)} 个 GBK 帮助文本）"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n构建失败: {exc}", file=sys.stderr)
        raise
