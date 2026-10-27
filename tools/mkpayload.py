#!/usr/bin/env python3
"""Build the single-file payload for palera1n's pongoOS "bootr":

    shim | header | DTB | uncompressed Image | room to move it | [initramfs overlay]

See shim/shim.c for the layout and what the shim does with it.

    python3 tools/mkpayload.py shim/shim.bin out/work/J71b-palera1n.dtb out/Linux.lzma out/ipadcastle.bin

--overlay DIR (repeatable) packs every file under DIR into a gzip cpio that
the kernel unpacks on top of its built-in ramdisk (e.g. overlay/rndis for
Windows hosts). Later directories win when they hold the same path.
"""
import argparse
import gzip
import lzma
import os
import struct
import sys

DTB_OFF, IMG_OFF, HDR_OFF = 0x10000, 0x20000, 0x0FF00
HDR_MAGIC = 0x4C534349  # "ICSL"
SZ_2M = 0x200000
UPLOAD_MAX = 128 * 1024 * 1024  # pongoOS UPLOADSZ_MAX


def cpio_newc(roots):
    """Files under the root directories as a gzip newc cpio. Later roots win
    when they hold the same path."""
    files = {}
    for root in roots:
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for f in sorted(names):
                path = os.path.join(dirpath, f)
                data = open(path, "rb").read()
                if data.startswith(b"#!"):
                    data = data.replace(b"\r\n", b"\n")  # scripts edited on Windows
                files[os.path.relpath(path, root).replace(os.sep, "/")] = data
    return cpio_files(files)


def cpio_files(files):
    """{path: bytes} as a gzip newc cpio. Every file gets mode 0755 and root
    ownership (Windows checkouts lose the exec bit). Directories in the paths
    are created first (mode 0755); existing ones in the ramdisk are kept."""
    out = bytearray()

    def entry(name, mode, data, ino):
        name = name.encode() + b"\0"
        fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0)
        out.extend(b"070701" + b"".join(b"%08X" % f for f in fields) + name)
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))

    ino = 0x1ca50000
    dirs = sorted({"/".join(n.split("/")[:i]) for n in files for i in range(1, n.count("/") + 1)})
    for d in dirs:
        ino += 1
        entry(d, 0o040755, b"", ino)
    for name, data in files.items():
        ino += 1
        entry(name, 0o100755, data, ino)
    entry("TRAILER!!!", 0, b"", 0)
    return gzip.compress(bytes(out), 9, mtime=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shim")
    ap.add_argument("dtb")
    ap.add_argument("kernel")
    ap.add_argument("out")
    ap.add_argument("--overlay", metavar="DIR", action="append", default=[])
    args = ap.parse_args()

    shim = open(args.shim, "rb").read()
    dtb = open(args.dtb, "rb").read()
    kernel = open(args.kernel, "rb").read()
    if kernel[56:60] != b"ARM\x64":
        kernel = lzma.decompress(kernel)
    if kernel[56:60] != b"ARM\x64":
        sys.exit(f"{args.kernel}: not an arm64 Image")
    rd = cpio_newc(args.overlay) if args.overlay else b""

    assert len(shim) <= HDR_OFF, "shim too big"
    assert len(dtb) <= IMG_OFF - DTB_OFF, "DTB too big"

    image_size = struct.unpack_from("<Q", kernel, 16)[0]
    # Room for the shim to slide the kernel up to the next 2 MiB boundary,
    # plus its BSS (image_size covers it). The overlay goes after that.
    rd_off = IMG_OFF + SZ_2M + max(image_size, len(kernel)) + 0x10000
    rd_off = (rd_off + 0x3FFF) & ~0x3FFF
    total = (rd_off + len(rd) + 0x3FFF) & ~0x3FFF
    if total > UPLOAD_MAX:
        sys.exit(f"payload {total} bytes exceeds pongoOS upload limit")

    buf = bytearray(total)
    buf[:len(shim)] = shim
    # touch_gen 0: the shim uses 2; load-linux.py --touch-gen patches it.
    struct.pack_into("<IIQQIIII", buf, HDR_OFF, HDR_MAGIC, len(dtb), len(kernel), total,
                     len(rd), rd_off if rd else 0, 0, 0)
    buf[DTB_OFF:DTB_OFF + len(dtb)] = dtb
    buf[IMG_OFF:IMG_OFF + len(kernel)] = kernel
    buf[rd_off:rd_off + len(rd)] = rd
    open(args.out, "wb").write(buf)
    extra = f", {len(rd)}-byte overlay" if rd else ""
    print(f"wrote {args.out}: {total // (1024 * 1024)} MiB{extra}")


if __name__ == "__main__":
    main()
