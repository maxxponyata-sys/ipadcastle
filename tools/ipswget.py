#!/usr/bin/env python3
"""Fetch single files out of a remote IPSW (zip) with HTTP range requests,
without downloading the whole multi-GB archive.

    python3 tools/ipswget.py URL list [PATTERN]
    python3 tools/ipswget.py URL get NAME OUTFILE
"""
import fnmatch
import struct
import sys
import urllib.request
import zlib


def fetch(url, start, length):
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
    with urllib.request.urlopen(req) as r:
        return r.read()


def size_of(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req) as r:
        return int(r.headers["Content-Length"])


def central_directory(url):
    total = size_of(url)
    tail = fetch(url, max(0, total - 0x10000), min(total, 0x10000))
    eocd = tail.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack_from("<II", tail, eocd + 12)
    loc = tail.rfind(b"PK\x06\x07")  # zip64 locator
    if loc >= 0:
        z64_off = struct.unpack_from("<Q", tail, loc + 8)[0]
        z64 = fetch(url, z64_off, 56)
        cd_size, cd_off = struct.unpack_from("<QQ", z64, 40)
    cd = fetch(url, cd_off, cd_size)
    entries, p = {}, 0
    while cd[p:p + 4] == b"PK\x01\x02":
        method, = struct.unpack_from("<H", cd, p + 10)
        csize, usize = struct.unpack_from("<II", cd, p + 20)
        nlen, xlen, clen = struct.unpack_from("<HHH", cd, p + 28)
        off, = struct.unpack_from("<I", cd, p + 42)
        name = cd[p + 46:p + 46 + nlen].decode()
        extra = cd[p + 46 + nlen:p + 46 + nlen + xlen]
        q = 0
        while q + 4 <= len(extra):  # zip64 extended info
            hid, hlen = struct.unpack_from("<HH", extra, q)
            if hid == 1:
                vals, r = [], q + 4
                for present in (usize == 0xFFFFFFFF, csize == 0xFFFFFFFF, off == 0xFFFFFFFF):
                    if present:
                        vals.append(struct.unpack_from("<Q", extra, r)[0])
                        r += 8
                if usize == 0xFFFFFFFF:
                    usize = vals.pop(0)
                if csize == 0xFFFFFFFF:
                    csize = vals.pop(0)
                if off == 0xFFFFFFFF:
                    off = vals.pop(0)
            q += 4 + hlen
        entries[name] = (method, csize, usize, off)
        p += 46 + nlen + xlen + clen
    return entries


def get(url, entries, name):
    method, csize, usize, off = entries[name]
    hdr = fetch(url, off, 30)
    nlen, xlen = struct.unpack_from("<HH", hdr, 26)
    data = fetch(url, off + 30 + nlen + xlen, csize)
    return zlib.decompress(data, -15) if method == 8 else data


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    url, cmd = sys.argv[1], sys.argv[2]
    entries = central_directory(url)
    if cmd == "list":
        pat = sys.argv[3] if len(sys.argv) > 3 else "*"
        for n, (_, _, usize, _) in sorted(entries.items()):
            if fnmatch.fnmatch(n, pat):
                print(f"{usize:12d}  {n}")
    elif cmd == "get":
        open(sys.argv[4], "wb").write(get(url, entries, sys.argv[3]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
