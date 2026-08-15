import collections
import pathlib
import struct
import zlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data.xp3"
XP3_MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"


def u16(data, pos):
    return struct.unpack_from("<H", data, pos)[0]


def u32(data, pos):
    return struct.unpack_from("<I", data, pos)[0]


def u64(data, pos):
    return struct.unpack_from("<Q", data, pos)[0]


def read_index(fp):
    fp.seek(len(XP3_MAGIC))
    next_offset = u64(fp.read(8), 0)
    complete = bytearray()
    while True:
        fp.seek(next_offset)
        flag = fp.read(1)[0]
        compressed = flag & 1
        continued = flag & 0x80
        if compressed:
            packed_size, raw_size = struct.unpack("<QQ", fp.read(16))
            block = zlib.decompress(fp.read(packed_size))
            if len(block) != raw_size:
                raise ValueError("bad index length")
        else:
            raw_size = struct.unpack("<Q", fp.read(8))[0]
            block = fp.read(raw_size)
        complete.extend(block)
        if not continued:
            break
        next_offset = struct.unpack("<Q", fp.read(8))[0]
    return bytes(complete)


def parse_files(index):
    pos = 0
    records = []
    while pos + 12 <= len(index):
        kind = index[pos : pos + 4]
        size = u64(index, pos + 4)
        payload = index[pos + 12 : pos + 12 + size]
        pos += 12 + size
        if kind != b"File":
            continue
        sub = 0
        rec = {"segments": []}
        while sub + 12 <= len(payload):
            skind = payload[sub : sub + 4]
            ssize = u64(payload, sub + 4)
            body = payload[sub + 12 : sub + 12 + ssize]
            sub += 12 + ssize
            if skind == b"info":
                rec["flags"] = u32(body, 0)
                rec["original_size"] = u64(body, 4)
                rec["archive_size"] = u64(body, 12)
                nchars = u16(body, 20)
                rec["name"] = body[22 : 22 + nchars * 2].decode("utf-16le")
            elif skind == b"segm":
                for off in range(0, len(body), 28):
                    rec["segments"].append(struct.unpack_from("<IQQQ", body, off))
            elif skind == b"adlr":
                rec["adler"] = u32(body, 0)
        records.append(rec)
    return records


def first_bytes(fp, record, limit=32):
    out = bytearray()
    for flags, archive_offset, original_size, archive_size in record["segments"]:
        fp.seek(archive_offset)
        data = fp.read(archive_size)
        if flags & 1:
            data = zlib.decompress(data)
        out.extend(data[: max(0, limit - len(out))])
        if len(out) >= limit:
            break
    return bytes(out)


def main():
    expected = {
        ".png": bytes.fromhex("89504e470d0a1a0a0000000d49484452"),
        ".ogg": b"OggS\x00",
        ".tlg": b"TLG",
        ".ttf": bytes.fromhex("00010000"),
        ".otf": b"OTTO",
        ".wmv": bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"),
    }
    with ARCHIVE.open("rb") as fp:
        magic = fp.read(len(XP3_MAGIC))
        if magic != XP3_MAGIC:
            raise ValueError("not an XP3 archive")
        records = parse_files(read_index(fp))
        print(f"records={len(records)}")
        by_ext = collections.defaultdict(list)
        for rec in records:
            by_ext[pathlib.PurePosixPath(rec["name"]).suffix.lower()].append(rec)

        for ext in sorted(by_ext):
            sample = by_ext[ext][0]
            data = first_bytes(fp, sample)
            print(f"{ext or '<none>':8} count={len(by_ext[ext]):4} hash={sample.get('adler', 0):08x} {sample['name']!r} head={data.hex()}")

        print("\nknown-header XOR patterns")
        for ext, head in expected.items():
            if ext not in by_ext:
                continue
            print(f"[{ext}]")
            for rec in by_ext[ext][:20]:
                data = first_bytes(fp, rec, len(head))
                xor = bytes(a ^ b for a, b in zip(data, head))
                print(f"  {rec.get('adler', 0):08x} xor={xor.hex()} name={rec['name']}")


if __name__ == "__main__":
    main()
