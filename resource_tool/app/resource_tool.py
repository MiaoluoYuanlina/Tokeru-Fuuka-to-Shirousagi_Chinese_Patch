from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "python" / "python.exe"
NODE = ROOT / "runtime" / "node" / "bin" / "node.exe"
CORE = ROOT / "core"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class Cancelled(Exception):
    pass


def clean_input(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return os.path.expandvars(value)


def use_dialog(callback) -> Path:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    try:
        selected = callback(root)
    finally:
        root.destroy()
    if not selected:
        raise Cancelled
    return Path(selected).expanduser().resolve()


def select_open_file(title: str, suffixes: set[str]) -> Path:
    from tkinter import filedialog

    pattern = " ".join(f"*{suffix}" for suffix in sorted(suffixes))
    return use_dialog(
        lambda root: filedialog.askopenfilename(
            parent=root,
            title=title,
            filetypes=[("支持的文件", pattern), ("所有文件", "*.*")],
        )
    )


def select_directory(title: str) -> Path:
    from tkinter import filedialog

    return use_dialog(lambda root: filedialog.askdirectory(parent=root, title=title, mustexist=False))


def select_save_file(title: str, suffix: str, initialfile: str) -> Path:
    from tkinter import filedialog

    return use_dialog(
        lambda root: filedialog.asksaveasfilename(
            parent=root,
            title=title,
            defaultextension=suffix,
            initialfile=initialfile,
            filetypes=[(f"{suffix} 文件", f"*{suffix}"), ("所有文件", "*.*")],
        )
    )


def existing_file(value: str | None, message: str, suffixes: set[str] | None = None) -> Path:
    path = Path(clean_input(value)).expanduser().resolve() if value else select_open_file(message, suffixes or {".*"})
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    if suffixes and path.suffix.lower() not in suffixes:
        raise ValueError(f"不支持的文件类型：{path.suffix}")
    return path


def existing_path(value: str | None, message: str) -> Path:
    if value:
        path = Path(clean_input(value)).expanduser().resolve()
    else:
        print("\nOCR 输入类型：")
        print("1. 递归扫描文件夹")
        print("2. 识别单张图片")
        while True:
            choice = input("请选择 [1-2]：").strip()
            if choice == "1":
                path = select_directory(message)
                break
            if choice == "2":
                path = select_open_file(message, IMAGE_SUFFIXES)
                break
            if choice.lower() in {"q", "quit", "exit", "取消"}:
                raise Cancelled
            print("请输入 1 或 2；输入 q 可取消。")
    if not path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    return path


def existing_directory(value: str | None, message: str) -> Path:
    path = Path(clean_input(value)).expanduser().resolve() if value else select_directory(message)
    if not path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    if not path.is_dir():
        raise NotADirectoryError(f"不是文件夹：{path}")
    return path


def output_directory(value: str | None, message: str) -> Path:
    path = Path(clean_input(value)).expanduser().resolve() if value else select_directory(message)
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_file(value: str | None, message: str, suffix: str, initialfile: str) -> Path:
    path = Path(clean_input(value)).expanduser().resolve() if value else select_save_file(message, suffix, initialfile)
    if not path.suffix:
        path = path.with_suffix(suffix)
    if path.suffix.lower() != suffix:
        raise ValueError(f"输出文件必须使用 {suffix} 扩展名：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run(command: list[str], title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}", flush=True)
    print(subprocess.list2cmdline(command), flush=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["KAZESHIRO_PADDLEOCR_RUNTIME"] = str(ROOT / "runtime" / "paddleocr_runtime")
    env["KAZESHIRO_PADDLE_GPU_RUNTIME"] = str(ROOT / "runtime" / "paddle_gpu_runtime")
    env["KAZESHIRO_OCR_MODEL_HOME"] = str(ROOT / "runtime" / "ocr_models")
    env.setdefault("KAZESHIRO_OCR_DEVICE", "auto")
    env["NODE_PATH"] = str(ROOT / "node_modules")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def decompile(args: argparse.Namespace) -> None:
    exe = existing_file(args.exe, "选择游戏 EXE（とける風花とシロうさぎ.exe 或 kazeshiro_demo.exe）", {".exe"})
    output = output_directory(args.resource_output, "选择游戏资源工作目录的输出位置")
    run(
        [str(PYTHON), str(CORE / "decompile_game.py"), "--exe", str(exe), "--output", str(output)],
        "反编译游戏资源并导出文本表格",
    )
    print(f"\n完成。游戏工作目录：{output}")
    print(f"剧情表格：{output / 'localization' / 'scenario_dialogue_zh_cn.xlsx'}")


def pack(args: argparse.Namespace) -> None:
    table = existing_file(args.table, "选择翻译表格（.xlsx 或 .tsv）", {".xlsx", ".tsv"})
    work = existing_directory(args.work_root, "选择反编译后的完整游戏工作目录")
    destination = output_file(args.patch_output, "选择 patch.xp3 的导出位置", ".xp3", "patch.xp3")
    run(
        [
            str(PYTHON), str(CORE / "build_patch_from_table.py"),
            "--table", str(table), "--work-root", str(work), "--tools-root", str(CORE),
        ],
        "从翻译表格构建补丁",
    )
    built = work / "patch.xp3"
    if not built.is_file():
        raise FileNotFoundError(f"构建程序没有生成补丁：{built}")
    if built.resolve() != destination.resolve():
        shutil.copy2(built, destination)
    print(f"\n完成。补丁：{destination}")


def ocr(args: argparse.Namespace) -> None:
    source = existing_path(args.input, "选择要 OCR 的图片或文件夹")
    if source.is_file() and source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"不支持的图片类型：{source.suffix}")
    output = output_file(args.ocr_output, "选择 OCR Excel 表格的保存位置", ".xlsx", "image_text_ocr.xlsx")
    work = output.parent / f"{output.stem}_work"
    run(
        [str(PYTHON), str(CORE / "generic_ocr.py"), "--input", str(source), "--output-dir", str(work)],
        "OCR 识别图片文字（自动尝试 0°、90°、270°）",
    )
    run(
        [str(NODE), str(CORE / "build_ocr_workbook.mjs"), "--data", str(work / "ocr_results.json"), "--output", str(output)],
        "生成 OCR Excel 表格",
    )
    print(f"\n完成。OCR 表格：{output}")


def render(args: argparse.Namespace) -> None:
    table = existing_file(args.table, "选择翻译完成的 OCR Excel 表格", {".xlsx"})
    output = output_directory(
        args.image_output,
        "选择处理后图片的导出目录（直接打包 TLG 时请选择工作目录的 extracted\\_tlg_png）",
    )
    work = output / "_resource_tool_work"
    work.mkdir(parents=True, exist_ok=True)
    data = work / "translations.json"
    run(
        [str(NODE), str(CORE / "read_ocr_workbook.mjs"), "--workbook", str(table), "--output", str(data)],
        "读取 OCR 翻译表格",
    )
    run(
        [str(PYTHON), str(CORE / "render_ocr_images.py"), "--data", str(data), "--output", str(output)],
        "回填中文并导出图片",
    )
    print(f"\n完成。处理后的图片：{output}")


ACTIONS = {"decompile": decompile, "pack": pack, "ocr": ocr, "render": render}


def choose_mode() -> str:
    print("\n风花与白兔 - 游戏资源汉化终端工具")
    print("=" * 46)
    print("1. 反编译资源并导出剧情表格")
    print("2. 从翻译表格打包 patch.xp3")
    print("3. OCR 识别单图或文件夹")
    print("4. 将 OCR 翻译表格应用到图片")
    print("0. 退出")
    choices = {"1": "decompile", "2": "pack", "3": "ocr", "4": "render"}
    while True:
        choice = input("请选择功能 [0-4]：").strip()
        if choice == "0":
            raise Cancelled
        if choice in choices:
            return choices[choice]
        print("请输入 0、1、2、3 或 4。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="风花与白兔游戏资源汉化终端工具")
    parser.add_argument("--mode", choices=ACTIONS, help="直接运行指定流程；省略时显示终端菜单")
    parser.add_argument("--exe", help="游戏 EXE 路径")
    parser.add_argument("--resource-output", help="反编译游戏工作目录")
    parser.add_argument("--table", help="翻译表格路径")
    parser.add_argument("--work-root", help="反编译后的完整游戏工作目录")
    parser.add_argument("--patch-output", help="patch.xp3 导出路径")
    parser.add_argument("--input", help="OCR 输入图片或文件夹")
    parser.add_argument("--ocr-output", help="OCR Excel 输出路径")
    parser.add_argument("--image-output", help="翻译图片导出目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        mode = args.mode or choose_mode()
        ACTIONS[mode](args)
        return 0
    except (Cancelled, EOFError, KeyboardInterrupt):
        print("\n操作已取消。")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"\n操作失败：子程序退出代码 {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    except Exception as exc:
        print(f"\n操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
