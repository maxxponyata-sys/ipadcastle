#!/usr/bin/env python3
"""Read one file out of an IPSW's APFS root filesystem image over HTTP,
without downloading the multi-GB archive. Needs `pip install libfsapfs-python`.

    python3 tools/ipswfs.py URL DMG-NAME /path/in/rootfs OUTFILE
"""
import os
import struct
import sys

import pyfsapfs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipswget  # noqa: E402

BLOCK = 1 << 20


class RemoteFile:
    """Seekable read-only file over HTTP range requests, cached per MiB."""

    def __init__(self, url, start, size):
        self.url, self.start, self.size, self.pos = url, start, size, 0
        self.cache = {}

    def _block(self, n):
        if n not in self.cache:
            off = n * BLOCK
            self.cache[n] = ipswget.fetch(self.url, self.start + off, min(BLOCK, self.size - off))
        return self.cache[n]

    def read(self, n=-1):
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        out = bytearray()
        while n > 0:
            b = self._block(self.pos // BLOCK)
            o = self.pos % BLOCK
            chunk = b[o:o + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def get_size(self):
        return self.size


class UdifFile:
    """The APFS partition of a UDIF .dmg, decompressing chunks on demand."""

    def __init__(self, raw):
        import base64
        import plistlib
        raw.seek(raw.size - 512)
        koly = raw.read(512)
        assert koly[:4] == b"koly", "not a UDIF image"
        xml_off, xml_len = struct.unpack_from(">QQ", koly, 0xD8)
        raw.seek(xml_off)
        plist = plistlib.loads(raw.read(xml_len))
        parts = plist["resource-fork"]["blkx"]
        part = max(parts, key=lambda p: len(p["Data"]))
        mish = base64.b64decode(part["Data"]) if isinstance(part["Data"], str) else part["Data"]
        assert mish[:4] == b"mish"
        count, = struct.unpack_from(">I", mish, 0xC8)
        self.chunks = []
        for i in range(count):
            t, _, sec, nsec, coff, clen = struct.unpack_from(">IIQQQQ", mish, 0xCC + 40 * i)
            if t == 0xFFFFFFFF:
                break
            self.chunks.append((sec * 512, nsec * 512, t, coff, clen))
        self.raw, self.pos, self.cache = raw, 0, {}
        self.size = max(s + n for s, n, *_ in self.chunks)

    def _chunk(self, i):
        if i not in self.cache:
            start, n, t, coff, clen = self.chunks[i]
            if t in (0, 2):
                data = bytes(n)
            else:
                self.raw.seek(coff)
                packed = self.raw.read(clen)
                if t == 1:
                    data = packed
                elif t == 0x80000005:
                    import zlib
                    data = zlib.decompress(packed)
                elif t == 0x80000007:
                    import liblzfse
                    data = liblzfse.decompress(packed)
                elif t == 0x80000008:
                    import lzma
                    data = lzma.decompress(packed)
                else:
                    raise ValueError(f"chunk type {t:#x}")
            if len(self.cache) > 64:
                self.cache.clear()
            self.cache[i] = data
        return self.cache[i]

    def read(self, n=-1):
        import bisect
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        starts = [c[0] for c in self.chunks]
        out = bytearray()
        while n > 0:
            i = bisect.bisect_right(starts, self.pos) - 1
            start, length = self.chunks[i][:2]
            data = self._chunk(i)
            o = self.pos - start
            piece = data[o:min(length, o + n)]
            if not piece:
                break
            out += piece
            self.pos += len(piece)
            n -= len(piece)
        return bytes(out)

    seek, tell, get_size = RemoteFile.seek, RemoteFile.tell, RemoteFile.get_size


def open_member(url, name):
    entries = ipswget.central_directory(url)
    method, csize, usize, off = entries[name]
    if method != 0:
        sys.exit(f"{name} is compressed in the zip; download it instead")
    hdr = ipswget.fetch(url, off, 30)
    nlen, xlen = struct.unpack_from("<HH", hdr, 26)
    return RemoteFile(url, off + 30 + nlen + xlen, usize)


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    url, dmg, path, out = sys.argv[1:]
    f = open_member(url, dmg)
    head = f.read(64)
    f.seek(0)
    if head[32:36] != b"NXSB":
        f = UdifFile(f)
        head = f.read(64)
        f.seek(0)
        if head[32:36] != b"NXSB":
            sys.exit(f"{dmg}: no APFS container found")
    container = pyfsapfs.container()
    container.open_file_object(f)
    for i in range(container.number_of_volumes):
        vol = container.get_volume(i)
        entry = vol.get_file_entry_by_path(path)
        if entry is not None:
            data = entry.read()
            open(out, "wb").write(data)
            print(f"{path}: {len(data)} bytes from volume {vol.name!r}")
            return
    sys.exit(f"{path} not found")


if __name__ == "__main__":
    main()
