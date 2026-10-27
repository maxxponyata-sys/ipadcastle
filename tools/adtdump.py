#!/usr/bin/env python3
"""Dump an Apple device tree (DeviceTree.*.im4p from an IPSW) as text.

    python3 tools/adtdump.py DeviceTree.j71bap.im4p [NODE-SUBSTRING]

IM4P payloads compressed with LZFSE ("bvx2") need `pip install pyliblzfse`.
"""
import struct
import sys


def pbz(data):
    """pbzx/pbze container: u64 chunk size, then (u64 raw, u64 packed, data)*."""
    import liblzfse
    import lzma
    out, p = bytearray(), 12
    while p < len(data):
        raw, packed = struct.unpack_from(">QQ", data, p)
        chunk = data[p + 16:p + 16 + packed]
        if packed == raw:
            out += chunk
        elif chunk[:4] == b"bvx2" or chunk[:4] == b"bvxn" or chunk[:4] == b"bvx1":
            out += liblzfse.decompress(chunk)
        else:
            out += lzma.decompress(chunk)
        p += 16 + packed
    return bytes(out)


def im4p_payload(data):
    if b"IM4P" not in data[:16]:
        return data  # already raw
    for magic in (b"pbzx", b"pbze"):
        i = data.find(magic, 0, 128)
        if i >= 0:
            return pbz(data[i:])
    i = data.find(b"bvx2")
    if i >= 0:
        import liblzfse
        return liblzfse.decompress(data[i:])
    # Uncompressed: the payload is the OCTET STRING after the description.
    p = data.find(b"\x04", data.find(b"IM4P") + 10)
    while p >= 0:
        n, q = data[p + 1], p + 2
        if n & 0x80:
            k = n & 0x7f
            n, q = int.from_bytes(data[q:q + k], "big"), q + k
        if n > 0x1000:
            return data[q:q + n]
        p = data.find(b"\x04", p + 1)
    raise ValueError("no IM4P payload")


def parse(buf, off=0):
    nprops, nchildren = struct.unpack_from("<II", buf, off)
    off += 8
    props = {}
    for _ in range(nprops):
        name = buf[off:off + 32].split(b"\0")[0].decode(errors="replace")
        length, = struct.unpack_from("<I", buf, off + 32)
        length &= 0x7FFFFFFF
        props[name] = buf[off + 36:off + 36 + length]
        off += 36 + ((length + 3) & ~3)
    children = []
    for _ in range(nchildren):
        child, off = parse(buf, off)
        children.append(child)
    return (props, children), off


def fmt(v):
    if v and v[-1:] == b"\0" and all(32 <= c < 127 for c in v[:-1].rstrip(b"\0")) and v[:-1].rstrip(b"\0"):
        parts = [p.decode() for p in v.split(b"\0") if p]
        return '"' + '", "'.join(parts) + '"'
    if len(v) % 4 == 0 and len(v) <= 256:
        return "<" + " ".join(f"0x{w:x}" for w in struct.unpack(f"<{len(v) // 4}I", v)) + ">"
    return v[:128].hex() + ("..." if len(v) > 128 else "")


def dump(node, path="", want=None, out=sys.stdout):
    props, children = node
    name = props.get("name", b"?\0").split(b"\0")[0].decode()
    path = f"{path}/{name}" if path else name
    if want is None or want in path:
        out.write(f"\n{path}\n")
        for k, v in props.items():
            out.write(f"    {k} = {fmt(v)}\n")
    for c in children:
        dump(c, path, want, out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    buf = im4p_payload(open(sys.argv[1], "rb").read())
    root, _ = parse(buf)
    dump(root, want=sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
