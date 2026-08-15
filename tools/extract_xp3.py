#!/usr/bin/env python3
"""Extract standard XP3 archives and verify every entry with its Adler-32."""

import argparse
import csv
import json
import os
import pathlib
import re
import struct
import time
import zlib


XP3_MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"|?*]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def unpack_u16(data, offset=0):
    return struct.unpack_from("<H", data, offset)[0]


def unpack_u32(data, offset=0):
    return struct.unpack_from("<I", data, offset)[0]


def unpack_u64(data, offset=0):
    return struct.unpack_from("<Q", data, offset)[0]


def read_index(stream):
    stream.seek(0)
    if stream.read(len(XP3_MAGIC)) != XP3_MAGIC:
        raise ValueError("文件不是标准 XP3 归档")

    index_offset = unpack_u64(stream.read(8))
    index = bytearray()
    while True:
        stream.seek(index_offset)
        flags_raw = stream.read(1)
        if not flags_raw:
            raise ValueError("XP3 索引偏移超出文件范围")
        flags = flags_raw[0]
        if flags & 1:
            packed_size, original_size = struct.unpack("<QQ", stream.read(16))
            block = zlib.decompress(stream.read(packed_size))
            if len(block) != original_size:
                raise ValueError("XP3 索引解压长度不匹配")
        else:
            original_size = unpack_u64(stream.read(8))
            block = stream.read(original_size)
            if len(block) != original_size:
                raise ValueError("XP3 索引读取不完整")
        index.extend(block)
        if not (flags & 0x80):
            break
        index_offset = unpack_u64(stream.read(8))
    return bytes(index)


def parse_index(index):
    records = []
    cursor = 0
    while cursor + 12 <= len(index):
        chunk_type = index[cursor:cursor + 4]
        chunk_size = unpack_u64(index, cursor + 4)
        chunk_end = cursor + 12 + chunk_size
        if chunk_end > len(index):
            raise ValueError("XP3 索引块长度无效")
        payload = index[cursor + 12:chunk_end]
        cursor = chunk_end
        if chunk_type != b"File":
            continue

        record = {"segments": []}
        sub_cursor = 0
        while sub_cursor + 12 <= len(payload):
            sub_type = payload[sub_cursor:sub_cursor + 4]
            sub_size = unpack_u64(payload, sub_cursor + 4)
            sub_end = sub_cursor + 12 + sub_size
            if sub_end > len(payload):
                raise ValueError("XP3 文件记录长度无效")
            body = payload[sub_cursor + 12:sub_end]
            sub_cursor = sub_end

            if sub_type == b"info":
                name_chars = unpack_u16(body, 20)
                record.update(
                    flags=unpack_u32(body, 0),
                    original_size=unpack_u64(body, 4),
                    archive_size=unpack_u64(body, 12),
                    name=body[22:22 + name_chars * 2].decode("utf-16le"),
                )
            elif sub_type == b"segm":
                if len(body) % 28:
                    raise ValueError("XP3 segm 块长度无效")
                for offset in range(0, len(body), 28):
                    record["segments"].append(
                        struct.unpack_from("<IQQQ", body, offset)
                    )
            elif sub_type == b"adlr":
                record["adler32"] = unpack_u32(body)

        required = {"name", "flags", "original_size", "archive_size", "adler32"}
        missing = required.difference(record)
        if missing or not record["segments"]:
            raise ValueError(f"XP3 文件记录缺少字段: {sorted(missing)}")
        records.append(record)
    return records


def safe_component(component):
    cleaned = INVALID_WINDOWS_CHARS.sub("_", component).rstrip(" .")
    if not cleaned:
        cleaned = "_"
    if cleaned.upper() in WINDOWS_RESERVED:
        cleaned = "_" + cleaned
    return cleaned


def output_path(output_root, archived_name, index, adler32):
    normalized = archived_name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".", "..")]
    parts = [safe_component(part) for part in parts]
    if not parts:
        parts = [f"unnamed_{index:04d}"]
    candidate = output_root.joinpath(*parts)
    # Keep enough headroom for Windows APIs without long-path support.
    if len(str(candidate.resolve())) >= 240:
        suffix = pathlib.PurePosixPath(parts[-1]).suffix
        candidate = output_root / "_long_names" / f"{index:04d}_{adler32:08x}{suffix}"
    return candidate


def extract_record(stream, record, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum = 1
    written = 0
    with destination.open("wb") as output:
        for segment_flags, archive_offset, original_size, archive_size in record["segments"]:
            stream.seek(archive_offset)
            data = stream.read(archive_size)
            if len(data) != archive_size:
                raise ValueError(f"归档段读取不完整: {record['name']}")
            if segment_flags & 1:
                data = zlib.decompress(data)
            if len(data) != original_size:
                raise ValueError(f"归档段解压长度不匹配: {record['name']}")
            output.write(data)
            checksum = zlib.adler32(data, checksum)
            written += len(data)
    return written, checksum & 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser(description="提取并校验标准 XP3 归档")
    parser.add_argument("archive", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()

    archive = args.archive.resolve()
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    started = time.time()

    manifest_rows = []
    extension_counts = {}
    verified = 0
    warning_records = 0
    failed = 0
    total_bytes = 0

    with archive.open("rb") as stream:
        records = parse_index(read_index(stream))
        print(f"发现 {len(records)} 个文件，开始提取……", flush=True)
        for index, record in enumerate(records, 1):
            destination = output_path(
                output_root, record["name"], index, record["adler32"]
            )
            size, actual_adler = extract_record(stream, record, destination)
            size_ok = size == record["original_size"]
            adler_ok = actual_adler == record["adler32"]
            is_protection_warning = (
                index == 1
                and not (record["flags"] & 0x80000000)
                and "This is a protected archive." in record["name"]
            )
            if size_ok and adler_ok:
                status = "verified"
            elif is_protection_warning:
                # XP3 protection deliberately inserts a malformed first record.
                # It is not a game resource, but retain its actual payload.
                status = "protection_warning_record"
            else:
                status = "failed"
            if status == "verified":
                verified += 1
            elif status == "protection_warning_record":
                warning_records += 1
            else:
                failed += 1
            total_bytes += size
            ext = pathlib.PurePosixPath(record["name"]).suffix.lower() or "<none>"
            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            manifest_rows.append(
                {
                    "index": index,
                    "archive_name": record["name"],
                    "extracted_path": destination.relative_to(output_root).as_posix(),
                    "size": size,
                    "expected_size": record["original_size"],
                    "archived_size": record["archive_size"],
                    "expected_adler32": f"{record['adler32']:08x}",
                    "actual_adler32": f"{actual_adler:08x}",
                    "flags": f"0x{record['flags']:08x}",
                    "segments": len(record["segments"]),
                    "status": status,
                }
            )
            if index % 250 == 0 or index == len(records):
                print(f"  {index}/{len(records)}", flush=True)

    manifest_path = output_root / "_xp3_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as manifest:
        writer = csv.DictWriter(manifest, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "archive": str(archive),
        "output": str(output_root),
        "files_total": len(manifest_rows),
        "files_verified": verified,
        "protection_warning_records": warning_records,
        "files_failed": failed,
        "extracted_bytes": total_bytes,
        "elapsed_seconds": round(time.time() - started, 3),
        "extension_counts": dict(sorted(extension_counts.items())),
    }
    with (output_root / "_xp3_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
