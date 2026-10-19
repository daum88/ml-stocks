#!/usr/bin/env python
"""Extract specific members from a ZIP64 archive split into parts, by central-directory
offset (avoids downloading parts that contain no needed files).

Usage: python scripts/extract_members.py --parts part00:path ... --out DIR --member NAME [...]
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import sys
import zlib

PART_SIZE = 2097152000


def read_cd_entry(path: pathlib.Path, cd_off_in04: int, targets: set[str]) -> dict:
    """Parse central directory entries, return {name: (lho, comp_size, method, crc)}."""
    with open(path, "rb") as f:
        f.seek(cd_off_in04)
        cd = f.read(852374)  # known cd_size for Kraken_OHLCVT_Full.zip
    found = {}
    pos = 0
    while pos + 46 <= len(cd):
        if cd[pos:pos + 4] != b"PK\x01\x02":
            break
        (sig, vmade, vneed, flags, method, mtime, mdate, crc, comp_size, uncomp_size,
         name_len, extra_len, comment_len, disk_start, int_attr, ext_attr, lho) = struct.unpack(
            "<IHHHHHHIIIHHHHHII", cd[pos:pos + 46])
        name = cd[pos + 46:pos + 46 + name_len].decode("utf-8", "replace")
        extra = cd[pos + 46 + name_len:pos + 46 + name_len + extra_len]
        real_lho = lho
        if lho == 0xFFFFFFFF or comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF:
            epos = 0
            while epos + 4 <= len(extra):
                tag, sz = struct.unpack("<HH", extra[epos:epos + 4])
                data = extra[epos + 4:epos + 4 + sz]
                if tag == 0x0001:
                    q = 0
                    if uncomp_size == 0xFFFFFFFF:
                        uncomp_size = struct.unpack("<Q", data[q:q + 8])[0]; q += 8
                    if comp_size == 0xFFFFFFFF:
                        comp_size = struct.unpack("<Q", data[q:q + 8])[0]; q += 8
                    if lho == 0xFFFFFFFF:
                        real_lho = struct.unpack("<Q", data[q:q + 8])[0]; q += 8
                epos += 4 + sz
        if name in targets:
            found[name] = (real_lho, comp_size, method, crc)
        pos += 46 + name_len + extra_len + comment_len
    return found


def read_at(parts: dict[int, pathlib.Path], whole_offset: int, length: int) -> bytes:
    """Read `length` bytes at `whole_offset` of the joined zip, spanning parts if needed."""
    out = bytearray()
    remaining = length
    off = whole_offset
    while remaining > 0:
        pi = off // PART_SIZE
        in_part = off % PART_SIZE
        p = parts[pi]
        with open(p, "rb") as f:
            f.seek(in_part)
            chunk = f.read(min(remaining, PART_SIZE - in_part))
        if not chunk:
            raise IOError(f"unexpected EOF at whole offset {off} (part {pi})")
        out += chunk
        off += len(chunk)
        remaining -= len(chunk)
    return bytes(out)


def extract(parts: dict[int, pathlib.Path], info: tuple, out_path: pathlib.Path) -> None:
    lho, comp_size, method, crc = info
    lh = read_at(parts, lho, 30)
    (sig, vneed, flags, m, mt, md, crc_lh, cs_lh, us_lh, name_len, extra_len) = struct.unpack(
        "<IHHHHHIIIHH", lh)
    data_off = lho + 30 + name_len + extra_len
    raw = read_at(parts, data_off, comp_size)
    if method == 8:
        data = zlib.decompress(raw, -15)
    elif method == 0:
        data = raw
    else:
        raise ValueError(f"unsupported compression method {method}")
    # verify CRC32
    if zlib.crc32(data) & 0xFFFFFFFF != crc:
        raise ValueError(f"CRC mismatch for {out_path.name}")
    out_path.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", required=True, help="comma list of partIdx:path")
    ap.add_argument("--cd-part", required=True, help="path to the part containing the central dir")
    ap.add_argument("--cd-offset", type=int, required=True, help="cd offset within cd-part")
    ap.add_argument("--out", required=True)
    ap.add_argument("--member", action="append", required=True)
    args = ap.parse_args()

    parts = {}
    for spec in args.parts.split(","):
        idx, p = spec.split(":", 1)
        parts[int(idx)] = pathlib.Path(p)
    cd_part = pathlib.Path(args.cd_part)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    found = read_cd_entry(cd_part, args.cd_offset, set(args.member))
    for name, info in found.items():
        print(f"extracting {name} ...", flush=True)
        extract(parts, info, out_dir / name)
    print(f"done: {len(found)} files")


if __name__ == "__main__":
    main()
