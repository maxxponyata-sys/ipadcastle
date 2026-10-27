#!/usr/bin/env python3
"""Compare two DTBs semantically: same nodes, same properties, with phandle
references resolved to node paths (so differing phandle numbering or node
order is ignored). Exit status 0 when equivalent."""
import struct
import sys

FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9

# property -> (stride, index of phandle cell within each stride); stride 0
# means a single phandle. Covers every reference used by the hx bindings.
PHANDLE_PROPS = {
    "interrupt-parent": (1, 0), "clocks": (1, 0), "pinctrl-0": (1, 0),
    "dwi": (1, 0), "lcd-supply": (1, 0), "charger": (1, 0), "nvmem": (1, 0),
    "hv-supply": (1, 0), "core-supply": (1, 0), "msi-parent": (1, 0),
    "sart-regions": (1, 0), "primary": (1, 0), "secondary": (1, 0),
    "gpios": (3, 0), "iommu-map": (4, 1),
}


def parse(path):
    blob = open(path, "rb").read()
    magic, _, off_struct, off_strings = struct.unpack(">IIII", blob[:16])
    assert magic == 0xD00DFEED, f"{path}: not a DTB"
    nodes, stack, pos = {}, [], off_struct

    def name_at(off):
        return blob[off_strings + off:blob.index(b"\0", off_strings + off)].decode()

    while True:
        (tok,) = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
            nodes["/" + "/".join(s for s in stack if s)] = {}
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            nodes["/" + "/".join(s for s in stack if s)][name_at(nameoff)] = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            return nodes


def normalize(nodes):
    by_phandle = {}
    for path, props in nodes.items():
        if "phandle" in props:
            by_phandle[struct.unpack(">I", props["phandle"])[0]] = path
    out = {}
    for path, props in nodes.items():
        norm = {}
        for name, val in props.items():
            if name in ("phandle", "linux,phandle"):
                continue
            key = "gpios" if name.endswith("-gpios") or name == "gpios" else name
            if key in PHANDLE_PROPS and len(val) % 4 == 0:
                cells = list(struct.unpack(f">{len(val) // 4}I", val))
                stride, idx = PHANDLE_PROPS[key]
                if key == "gpios":
                    # gpio specifiers: <&ctrl pin flags>, ctrl cells = 2 here
                    stride = 3
                norm[name] = tuple(
                    by_phandle.get(c, c) if i % stride == idx else c
                    for i, c in enumerate(cells))
            else:
                norm[name] = val
        out[path] = norm
    return out


def main():
    a, b = (normalize(parse(p)) for p in sys.argv[1:3])
    diffs = []
    for path in sorted(set(a) | set(b)):
        if path not in a or path not in b:
            diffs.append(f"node {path} only in {'second' if path not in a else 'first'}")
            continue
        for prop in sorted(set(a[path]) | set(b[path])):
            if a[path].get(prop) != b[path].get(prop):
                diffs.append(f"{path}:{prop}: {a[path].get(prop)!r} != {b[path].get(prop)!r}")
    print("\n".join(diffs) if diffs else "equivalent")
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
