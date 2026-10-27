#!/usr/bin/env python3
"""Read Apple multitouch firmware (*.mtprops) and its embedded config.

    python3 tools/mtprops.py J71b.mtprops            show personalities and the config
    python3 tools/mtprops.py J71b.mtprops K1F19,4 OUTDIR
        write OUTDIR/fw.bin (Constructed Firmware) and OUTDIR/config.txt
    python3 tools/mtprops.py export J71b.mtprops ROOT
        write ROOT/usr/share/firmware/multitouch/J71b.{fw,json} for ipad-touchd

The "Firmware Config" blob is IOKit-serialized XML (with ID/IDREF sharing),
which plistlib can't read, so it is parsed here.
"""
import os
import plistlib
import sys
import xml.etree.ElementTree as ET


def parse_iokit_xml(data):
    """IOKit XML (dict/array/integer/string/data/true/false, ID/IDREF) -> Python."""
    root = ET.fromstring(b"<root>" + data.strip(b"\0") + b"</root>")[0]
    ids = {}

    def conv(e):
        if "IDREF" in e.attrib:
            return ids[e.attrib["IDREF"]]
        t = e.tag
        if t == "dict":
            kids = list(e)
            v = {kids[i].text: conv(kids[i + 1]) for i in range(0, len(kids), 2)}
        elif t == "array":
            v = [conv(k) for k in e]
        elif t == "integer":
            v = int(e.text, 0)
        elif t == "string":
            v = e.text or ""
        elif t == "data":
            import base64
            v = base64.b64decode(e.text or "")
        elif t in ("true", "false"):
            v = t == "true"
        else:
            raise ValueError(t)
        if "ID" in e.attrib:
            ids[e.attrib["ID"]] = v
        return v

    return conv(root)


def load(path, personality=None):
    props = plistlib.loads(open(path, "rb").read())
    if personality is None:
        personality = next(iter(props))
    fw = props[personality]
    cfg = parse_iokit_xml(fw["Firmware Config"]) if "Firmware Config" in fw else {}
    return personality, fw, cfg


def fmt(v, pre="  "):
    if isinstance(v, dict):
        return "".join(f"\n{pre}{k}: {fmt(w, pre + '  ')}" for k, w in v.items())
    if isinstance(v, list):
        return "".join(f"\n{pre}- {fmt(w, pre + '  ')}" for w in v)
    if isinstance(v, int) and not isinstance(v, bool):
        return hex(v)
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    return repr(v)


def export(path, root):
    """Firmware blob plus the sequences ipad-touchd needs, as plain JSON (the
    ramdisk has no parser for IOKit XML)."""
    import json
    pers, fw, cfg = load(path)
    blob = fw["Constructed Firmware"]
    if isinstance(blob, list):
        sys.exit("multi-blob firmware (iPhone style): use Corellium's hx-touchd")
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(root, "usr", "share", "firmware", "multitouch")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, name + ".fw"), "wb").write(blob)
    info = {
        "personality": pers,
        "firmware_file": name + ".fw",
        "firmware_version": fw.get("Constructed Firmware Version", ""),
        "packet_type": fw.get("PreconstructedBootloadPacketType", ""),
        "calibration": [{"address": c["Address"], "max_size": c["Max Size"],
                         "provider": c["Provider"], "name": c.get("Name", "")}
                        for c in cfg.get("Calibration Sequence", [])],
        "boot": [{"action": b["Action"]} if "Action" in b else
                 dict({"address": b["Address"], "value": b["Value"]},
                      **({"mask": b["Mask"]} if "Mask" in b else {}))
                 for b in cfg.get("Boot Sequence", [])],
    }
    open(os.path.join(out, name + ".json"), "w").write(json.dumps(info, indent=1))
    print(f"wrote {out}/{name}.fw ({len(blob)} bytes) and {name}.json")


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "export":
        return export(sys.argv[2], sys.argv[3])
    if len(sys.argv) not in (2, 4):
        sys.exit(__doc__)
    pers, fw, cfg = load(sys.argv[1], sys.argv[2] if len(sys.argv) == 4 else None)
    keep = {k: v for k, v in cfg.items() if k not in ("Interface Config", "Memory Dump")}
    text = f"personality {pers}\n" + "".join(
        f"{k}: {fmt(v) if not isinstance(v, (bytes, dict, list)) else fmt(v)}\n" for k, v in fw.items()
        if k != "Firmware Config") + "config:" + fmt(keep) + "\n"
    if len(sys.argv) == 4:
        os.makedirs(sys.argv[3], exist_ok=True)
        open(os.path.join(sys.argv[3], "fw.bin"), "wb").write(fw["Constructed Firmware"])
        open(os.path.join(sys.argv[3], "config.txt"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
