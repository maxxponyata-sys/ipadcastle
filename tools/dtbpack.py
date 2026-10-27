#!/usr/bin/env python3
"""Pack/unpack Project Sandcastle "dtbpack" files.

Format (as read by pongoOS fdt_select_dtree):
    "Cows"
    repeated: <target-type>\0 <u32 big-endian length> <dtb bytes>
    "\0"  (terminator)

pongoOS picks the entry whose name equals the device's iBoot
/device-tree/target-type (e.g. "D10" for iPhone 7, "J71b" for iPad 6 Wi-Fi).
"""
import argparse
import os
import struct
import sys

MAGIC = b"Cows"


def unpack(path):
    data = open(path, "rb").read()
    if data[:4] != MAGIC:
        sys.exit(f"{path}: not a dtbpack (missing 'Cows' magic)")
    pos, entries = 4, []
    while data[pos] != 0:
        end = data.index(b"\0", pos)
        name = data[pos:end].decode()
        (length,) = struct.unpack(">I", data[end + 1:end + 5])
        entries.append((name, data[end + 5:end + 5 + length]))
        pos = end + 5 + length
    return entries


def pack(entries):
    out = bytearray(MAGIC)
    for name, blob in entries:
        out += name.encode() + b"\0" + struct.pack(">I", len(blob)) + blob
    out += b"\0"
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="list entries")
    p.add_argument("pack")

    p = sub.add_parser("unpack", help="extract every entry to <outdir>/<name>.dtb")
    p.add_argument("pack")
    p.add_argument("outdir")

    p = sub.add_parser("pack", help="build a pack from NAME=file.dtb pairs")
    p.add_argument("out")
    p.add_argument("entries", nargs="+", metavar="NAME=FILE")

    args = ap.parse_args()
    if args.cmd == "list":
        for name, blob in unpack(args.pack):
            print(f"{name}\t{len(blob)} bytes")
    elif args.cmd == "unpack":
        os.makedirs(args.outdir, exist_ok=True)
        for name, blob in unpack(args.pack):
            open(os.path.join(args.outdir, name + ".dtb"), "wb").write(blob)
            print(f"{name}.dtb")
    else:
        entries = []
        for spec in args.entries:
            name, _, path = spec.partition("=")
            entries.append((name, open(path, "rb").read()))
        open(args.out, "wb").write(pack(entries))
        print(f"wrote {args.out}: " + ", ".join(n for n, _ in entries))


if __name__ == "__main__":
    main()
