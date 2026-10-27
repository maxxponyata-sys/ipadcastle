#!/usr/bin/env python3
"""Checks tools/load-linux.py dt_bytes() against output formatted exactly
like pongoOS's dt_cbp() (src/drivers/dt/dt.c, default byte-wise mode).

    python tests/dtparse_test.py
"""
import importlib.machinery
import importlib.util
import os
import random
import sys

here = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("ll", os.path.join(here, "..", "tools", "load-linux.py"))
ll = importlib.util.module_from_spec(importlib.util.spec_from_loader("ll", loader))
loader.exec_module(ll)

KEY_LEN = 32


def pongo_dump(key, val):
    """Port of dt_cbp() for a non-printable value, size flag 0."""
    if all(0x20 <= c < 0x7F for c in val.rstrip(b"\0")) and val.rstrip(b"\0"):
        return f"{key:<{KEY_LEN}} {val.rstrip(bytes(1)).decode()}\n"
    lines, k = [], key
    xs, cs = [" "] * 49, [""] * 17
    for i in (2, 5, 8, 11, 14, 17, 20, 23, 24, 27, 30, 33, 36, 39, 42, 45):
        xs[i] = " "
    for i, c in enumerate(val):
        is_ = i % 16
        ix = 3 * is_ + (1 if is_ >= 8 else 0)
        xs[ix], xs[ix + 1] = "%02x" % c
        cs[is_] = chr(c) if 0x20 <= c < 0x7F else "."
        if is_ == 15:
            lines.append(f"{k:<{KEY_LEN}} {''.join(xs):<49}  |{''.join(cs[:16])}|")
            k = ""
    if len(val) % 16:
        is_ = len(val) % 16
        ix = 3 * is_ + (1 if is_ >= 8 else 0)
        lines.append(f"{k:<{KEY_LEN}} {''.join(xs[:ix]):<49}  |{''.join(cs[:is_])}|")
    return "\n".join(lines) + "\n"


fails = 0
random.seed(1)
for n in (16, 37, 0x400, 0x1000 - 3):
    val = bytes(random.randrange(256) for _ in range(n))
    text = "pongoOS> dt multi-touch multi-touch-calibration\r\n" + pongo_dump("multi-touch-calibration", val) + "pongoOS> "
    got = ll.dt_bytes(text)
    ok = got == val
    fails += not ok
    print(("ok:   " if ok else "FAIL: ") + f"{n}-byte property parsed back exactly")
got = ll.dt_bytes("pongoOS> dt multi-touch x\r\n" + pongo_dump("multi-touch-calibration", b"syscfg/MtCl\0") + "pongoOS> ")
ok = got is None
fails += not ok
print(("ok:   " if ok else "FAIL: ") + "unfilled syscfg reference reads as missing")
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
