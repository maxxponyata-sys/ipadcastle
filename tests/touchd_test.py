#!/usr/bin/env python
"""Offline tests for overlay/touch/usr/bin/ipad-touchd (Python 2 and 3).

    python tests/touchd_test.py [DIR-WITH-*.mtprops]

1. load_packet() rebuilds Apple's firmware blobs byte for byte from their
   payloads: iPad 6 (K1HBPP14) with fmt "hbpp14", iPhone 7 and iPod touch 7
   (Z2) with fmt "z2". Needs the .mtprops files (tools/ipswfs.py fetches
   them); skipped if absent.
2. The whole boot flow runs against a fake /dev/hx-touch that answers like
   a controller, so every code path is exercised without the iPad.
"""
from __future__ import print_function

import json
import os
import plistlib
import shutil
import struct
import sys
import tempfile

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, "..", "overlay", "touch", "usr", "bin", "ipad-touchd")
try:
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("touchd", src)
    touchd = importlib.util.module_from_spec(importlib.util.spec_from_loader("touchd", loader))
    loader.exec_module(touchd)
except ImportError:  # Python 2
    import imp
    touchd = imp.load_source("touchd", src)
RealTouch = touchd.Touch
fails = []


def check(cond, what):
    print(("ok:   " if cond else "FAIL: ") + what)
    if not cond:
        fails.append(what)


def unswap(b):
    return touchd.swap16(b)  # swapping twice is the identity


def read_plist(path):
    data = open(path, "rb").read()
    return plistlib.loads(data) if hasattr(plistlib, "loads") else plistlib.readPlistFromString(data)


def blob_roundtrip(adt_dir):
    cases = (("J71b", "K1F19,4", "hbpp14"), ("D10", "C1F5D,2", "z2"), ("N112", "C1F58,1", "z2"))
    for name, pers, fmt in cases:
        path = os.path.join(adt_dir, name + ".mtprops")
        if not os.path.exists(path):
            print("skip: %s not found" % path)
            continue
        fw = read_plist(path)[pers]["Constructed Firmware"]
        for i, blob in enumerate(fw if isinstance(fw, list) else [fw]):
            blob = bytearray(blob.data if hasattr(blob, "data") else blob)
            words = (blob[4] << 8) | blob[5]
            b = blob[6:10]
            addr = (b[0] << 8) | b[1] | (b[2] << 24) | (b[3] << 16)
            payload = unswap(blob[12:12 + words * 4])
            rebuilt = touchd.load_packet(addr, payload, fmt)
            check(rebuilt == blob, "%s blob %d: load_packet(%#x, %d bytes, %s) rebuilds Apple's %d-byte blob"
                  % (name, i, addr, len(payload), fmt, len(blob)))


class FakeTouch(object):
    """Answers like a controller: boot IRQ, then report D9 with metrics."""
    METRICS = (120, 9880, 60, 9940)  # left, right, top, bottom

    def __init__(self, mt_type_ok):
        self.mt_type_ok = mt_type_ok
        self.log = []
        self.pending = None

    def close(self):
        pass

    def ioctl(self, req, arg=0):
        self.log.append(("ioctl", req, arg))

    def cs(self, on):
        pass

    def wait_irq(self, ms):
        return True

    def xfer(self, data):
        return bytearray(len(data))

    def framed(self, data):
        data = bytearray(data)
        self.log.append(("spi", bytes(data[:4]), len(data)))
        rx = bytearray(len(data))
        if len(data) == 16 and data[0] == touchd.MT_REP_INFO:
            if self.pending == "info":
                rx[2], rx[3], rx[4] = 0, 16, 0  # supported, 16 bytes
            self.pending = "info"
        elif len(data) == 21:
            if self.mt_type_ok == 1:
                ok = data[0] == touchd.MT_CTRL_READ_LONG and data[1] == 0xD9
            else:
                ok = data[0] == 0xA5
            if ok:
                d9 = bytearray(16)
                l, r, t, b = self.METRICS
                struct.pack_into("<4h", d9, 8, l, t, r, b)  # iPad layout: min x, min y, max x, max y
                rx[3:19] = d9
        return rx

    def z2(self, cmd=None):
        return RealTouch.__dict__["z2"](self, cmd)


def fake_run(mt_type_ok, adt_dir):
    tmp = tempfile.mkdtemp()
    try:
        fwdir = os.path.join(tmp, "fw")
        caldir = os.path.join(tmp, "cal")
        os.makedirs(fwdir)
        os.makedirs(caldir)
        open(os.path.join(fwdir, "J71b.fw"), "wb").write(touchd.load_packet(0x100000, bytearray(range(256)) * 4))
        cfg = {"personality": "K1F19,4", "firmware_file": "J71b.fw", "firmware_version": "test",
               "packet_type": "K1HBPP14",
               "calibration": [{"address": 0x100400, "max_size": 0x1000, "provider": "multi-touch-calibration"},
                               {"address": 0x102a00, "max_size": 0x200, "provider": "multitouch-to-display-offset"}],
               "boot": [{"address": 0x102c00, "value": 0},
                        {"address": 0x400b0000, "mask": 1, "value": 1},
                        {"action": "RequestCalibration"}]}
        json.dump(cfg, open(os.path.join(fwdir, "J71b.json"), "w"))
        open(os.path.join(caldir, "multi-touch-calibration.bin"), "wb").write(b"\x11" * 0x30)
        touchd.FW_DIR, touchd.CAL_DIR = fwdir, caldir
        # Fake /sys/class/gpio: a small chip that must be ignored, and the SoC block at 288.
        gpio = os.path.join(tmp, "gpio")
        for name, base, n in (("gpiochip496", 496, 16), ("gpiochip288", 288, 224)):
            os.makedirs(os.path.join(gpio, name))
            for f, v in (("base", base), ("ngpio", n), ("label", name)):
                open(os.path.join(gpio, name, f), "w").write("%s\n" % v)
        for pin in (288 + 0x91, 288 + 0x1d):
            os.makedirs(os.path.join(gpio, "gpio%d" % pin))
        open(os.path.join(gpio, "export"), "w").close()
        touchd.GPIO_SYSFS = gpio
        fake = FakeTouch(mt_type_ok)
        touchd.Touch = lambda: fake
        sleep = touchd.time.sleep
        state = {"handed": False}

        def fake_sleep(s):
            if s >= 3600:
                state["handed"] = True
                raise KeyboardInterrupt
        touchd.time.sleep = fake_sleep
        try:
            sys.argv = ["ipad-touchd", "--kernel"]
            touchd.main()
        except KeyboardInterrupt:
            pass
        finally:
            touchd.time.sleep = sleep
        levels = [open(os.path.join(gpio, "gpio%d" % p, "direction")).read() for p in (288 + 0x91, 288 + 0x1d)]
        check(levels == ["high", "high"], "mt_type %d: power_ana and power_ldo GPIOs driven high on the SoC chip" % mt_type_ok)
        ioctls = [e for e in fake.log if e[0] == "ioctl"]
        spi = [e for e in fake.log if e[0] == "spi"]
        check(state["handed"], "mt_type %d: boot flow reaches the hand-over to the kernel" % mt_type_ok)
        check(any(e[1] == touchd.HXT_IOC_READY for e in ioctls), "mt_type %d: HXT_IOC_READY issued" % mt_type_ok)
        met = [e for e in ioctls if e[1] == touchd.HXT_IOC_METRICS]
        check(met and struct.unpack("<4i", met[0][2]) == FakeTouch.METRICS,
              "mt_type %d: metrics from report D9 passed to the kernel" % mt_type_ok)
        kinds = [s[1] for s in spi]
        # kinds[0] is the boot ROM hello (4 zero bytes)
        check(kinds[1:3] == [b"\x1a\xa1\x18\xe1", b"\x18\xe1\x30\x01"],
              "mt_type %d: prelude then firmware load packet" % mt_type_ok)
        check(sum(1 for k in kinds if k[:2] == b"\x1e\x33") == 2, "mt_type %d: two register writes" % mt_type_ok)
        check(b"\x1f\x01" in [k[:2] for k in kinds], "mt_type %d: RequestCalibration sent" % mt_type_ok)
    finally:
        shutil.rmtree(tmp)


def regwr_vs_c():
    """Vectors from Corellium's mtfw_item_add_regwr() (tests/regwr_vectors.txt)."""
    path = os.path.join(here, "regwr_vectors.txt")
    if not os.path.exists(path):
        print("skip: %s not found" % path)
        return
    for line in open(path):
        a, m, v, expect = line.split()
        got = touchd.regwr_packet(int(a, 16), int(m, 16), int(v, 16))
        check(bytearray(got) == bytearray.fromhex(expect) if hasattr(bytearray, "fromhex") else False,
              "regwr(%s, %s, %s) matches the C implementation" % (a, m, v))


def real_d9():
    """Report D9 as the iPad 6 sent it on its first successful boot."""
    d9 = bytearray.fromhex("99390000ca4c000059ff59fff038214c")
    m = touchd.metrics_from_d9(d9, "ipad")
    check(m == (-167, 14576, -167, 19489), "iPad D9 -> left -167 right 14576 top -167 bottom 19489 (got %r)" % (m,))
    check(m[1] - m[0] == 14743 and m[3] - m[2] == 19656,
          "iPad D9 ranges match its panel size fields (147.45 x 196.58 mm)")


def real_frames():
    """Touch frames as the iPad 6 sent them (first 59 payload bytes, from --dump)."""
    one = bytearray.fromhex("ea0156 00bf 9003500076132004ad0000000004279702000000300000000000010010010000ebff0000"
                            "01030300ebd72347a50d8d47".replace(" ", ""))
    t = touchd.parse_touches(one[5:])
    check(t is not None and len(t) == 1 and t[0][:2] == (1, 3) and abs(t[0][2] - 41943.9) < 1 and abs(t[0][3] - 72219.3) < 1,
          "one-finger frame -> id 1, state 3 (new), x 41944 y 72219 um (got %r)" % (t,))
    two = bytearray.fromhex("ea02 8600 8e90 0380 0076 0520 0491 0800 0000 0427 9702 0000 0060 0000 0000 0002 0010 0100 00f3"
                            "ff00 000b 0403 0086 17da 4708 7a86 47".replace(" ", ""))
    t = touchd.parse_touches(two[5:])
    check(t is not None and len(t) == 1 and t[0][:2] == (0x0b, 4),
          "two-finger frame (truncated) -> first record id 11, state 4 (down) (got %r)" % (t,))
    check(touchd.parse_touches(bytearray.fromhex("9001 0c00 5002 0000".replace(" ", ""))) is None,
          "non-touch report ignored")


class FrameTouch(object):
    """Replays one framed packet for read_frame()."""

    def __init__(self, packet):
        self.packet, self.reads = bytearray(packet), []

    def framed(self, data):
        return bytearray(len(data))

    def cs(self, on):
        pass

    def xfer(self, data):
        n = len(data)
        out, self.packet = self.packet[:n], self.packet[n:]
        return out + bytearray(n - len(out))


def frame_reader():
    payload = bytearray(range(0x90, 0x90 + 84 - 2)) + bytearray(2)
    payload[0], payload[1] = 0x90, 0x03
    s = sum(payload[:-2])
    payload[-2], payload[-1] = s & 255, (s >> 8) & 255
    hdr = bytearray([0xEA, 0x01, len(payload) & 255, len(payload) >> 8, 0])
    hdr[4] = (-sum(hdr[:4])) & 0xFF
    got = touchd.read_frame(FrameTouch(hdr + payload), 0)
    check(got == payload[:-2], "read_frame reassembles an 84-byte packet across both transfers and checks its sum")
    bad = bytearray(hdr + payload)
    bad[-1] ^= 1
    check(touchd.read_frame(FrameTouch(bad), 0) is None, "read_frame rejects a bad checksum")


if __name__ == "__main__":
    adt = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "out", "adt")
    real_d9()
    real_frames()
    frame_reader()
    blob_roundtrip(adt)
    regwr_vs_c()
    fake_run(2, adt)
    fake_run(1, adt)
    print("\n%d failure(s)" % len(fails))
    sys.exit(1 if fails else 0)
