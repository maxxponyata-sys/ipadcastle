#!/usr/bin/env python3
"""Send Sandcastle Linux to a device sitting in pongoOS and boot it.

palera1n route (iPadOS 15-17): one payload built by tools/mkpayload.py,
booted with pongoOS "bootr" through shim/:

    sudo python3 tools/load-linux.py --payload out/ipadcastle.bin

checkra1n route (older iOS, checkra1n's pongoOS has a Linux loader). Same USB
protocol as Corellium's load-linux:

    sudo python3 tools/load-linux.py out/Linux.lzma out/dtbpack

Requires pyusb (Debian: python3-usb) and libusb. On Windows, pongoOS needs
the WinUSB or libusbK driver (install it with Zadig) and libusb-1.0.dll,
which `pip install libusb-package` provides.
"""
import argparse
import os
import struct
import sys
import time

import usb.backend.libusb1
import usb.core
import usb.util

# Bootargs baked into every Sandcastle tree. pongoOS replaces /chosen/bootargs
# with whatever "linux_cmdline" was set to (an empty string if never set), so
# always send it.
DEFAULT_CMDLINE = ("earlycon=hx_uart,0x20a0c0000 console=tty0 console=ttyHX0 "
                   "selinux=1 enforcing=0 androidboot.selinux=permissive "
                   "printk.devkmsg=on androidboot.hardware=ranchu")

PONGO_VID, PONGO_PID = 0x05AC, 0x4141
CHUNK = 1024 * 1024  # bulk writes in pieces; one 53 MiB transfer is too much for some Windows stacks


def libusb_backend():
    """libusb-1.0 from tools/bin, then from the libusb-package wheel, then
    pyusb's default search (system libusb on Linux)."""
    dll = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "libusb-1.0.dll")
    if os.name == "nt" and os.path.exists(dll):
        return usb.backend.libusb1.get_backend(find_library=lambda _: dll)
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except ImportError:
        return None


def find_pongo(attempts=30):
    backend = libusb_backend()
    waiting = False
    for _ in range(attempts):
        dev = usb.core.find(idVendor=PONGO_VID, idProduct=PONGO_PID, backend=backend)
        if dev is None:
            if not waiting:
                print("Waiting for pongoOS (run checkra1n -cp / palera1n -p first)...")
                waiting = True
            time.sleep(2)
            continue
        try:
            dev.set_configuration()
            return dev
        except NotImplementedError:
            return dev  # WinUSB can't select a configuration; config 1 is already active
        except usb.core.USBError as e:
            # Right after palera1n exits, pongoOS can still be re-enumerating
            # (EIO / "no such device" on open). Drop the handle and retry.
            print(f"pongoOS not ready yet ({e}), retrying...")
            usb.util.dispose_resources(dev)
            time.sleep(2)
    sys.exit("pongoOS did not answer on USB. Check the cable (and on Windows, that "
             "pongoOS has the WinUSB or libusbK driver), or hard-reboot the iPad "
             "(Power + Home) and start again.")


def command(dev, line):
    dev.ctrl_transfer(0x21, 4, 0, 0, 0)
    dev.ctrl_transfer(0x21, 3, 0, 0, line + "\n")


def run(dev, line, timeout=15):
    """Run a pongoOS shell command and return everything it printed. stdout
    is switched to blocking so nothing is dropped from its 4 KiB buffer."""
    dev.ctrl_transfer(0x21, 4, 1, 0, 0)
    while dev.ctrl_transfer(0xA1, 1, 0, 0, 0x1000):
        pass  # drain old output
    dev.ctrl_transfer(0x21, 3, 0, 0, line + "\n")
    out, end = bytearray(), time.time() + timeout
    while time.time() < end:
        chunk = bytes(dev.ctrl_transfer(0xA1, 1, 0, 0, 0x1000))
        out += chunk
        if not chunk:
            if out.rstrip().endswith(b"pongoOS>"):
                break
            time.sleep(0.02)
    dev.ctrl_transfer(0x21, 4, 0xFFFF, 0, 0)
    return out.decode("ascii", "replace")


# Apple device tree properties of the touch controller that iBoot fills from
# syscfg ("syscfg/MtCl" etc.). ipad-touchd loads them as calibration.
TOUCH_CAL_PROPS = ("multi-touch-calibration", "multitouch-to-display-offset",
                   "firefly-calibration", "pressure-effect-correction")


def dt_bytes(text):
    """Bytes of one property from pongoOS "dt <node> <prop>" output (a hex
    dump, 16 bytes a line, ascii column after "|"). None if it printed a
    string (iBoot left the "syscfg/..." reference: no data)."""
    data, seen = bytearray(), False
    for line in text.splitlines():
        if not line.rstrip().endswith("|"):
            continue
        seen = True
        for tok in line.split()[0 if line[:1] == " " else 1:]:
            if tok.startswith("|") or len(tok) != 2:
                break
            data.append(int(tok, 16))
    return bytes(data) if seen else None


def read_touch_cal(dev):
    """Calibration blobs from the live Apple device tree, plus the whole
    multi-touch node as text for debugging."""
    files = {"etc/hw/touch-adt.txt": run(dev, "dt multi-touch").encode()}
    for prop in TOUCH_CAL_PROPS:
        data = dt_bytes(run(dev, f"dt multi-touch {prop}"))
        if data:
            files[f"etc/hw/touch-cal/{prop}.bin"] = data
        print(f"  {prop}: {f'{len(data)} bytes' if data else 'not in device tree'}")
    return files


def add_overlay(payload, files):
    """Append a gzip cpio with these files to the payload's ramdisk overlay
    (the kernel unpacks concatenated archives in order)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mkpayload
    hdr = mkpayload.HDR_OFF
    rd_size, rd_off = struct.unpack_from("<II", payload, hdr + 24)
    if not rd_size:
        sys.exit("this payload has no overlay to add to; rebuild it with build.sh")
    extra = mkpayload.cpio_files(files)
    end = rd_off + rd_size + len(extra)
    total = (end + 0x3FFF) & ~0x3FFF
    buf = bytearray(payload[:rd_off + rd_size]) + extra
    buf += bytes(total - len(buf))
    struct.pack_into("<Q", buf, hdr + 16, total)
    struct.pack_into("<I", buf, hdr + 24, rd_size + len(extra))
    return bytes(buf)


def start_upload(dev, size):
    """Discard old data and announce the upload size. pongoOS refuses (stalls)
    the size request while an earlier upload is still waiting for data."""
    for attempt in range(2):
        dev.ctrl_transfer(0x21, 2, 0, 0, 0)
        try:
            dev.ctrl_transfer(0x21, 1, 0, 0, struct.pack("I", size))
            return
        except usb.core.USBError as e:
            if e.errno != 32 or attempt:
                break
        # An interrupted upload: a short packet ends it, then discard.
        try:
            dev.write(2, b"\0", 2000)
        except usb.core.USBError:
            pass
    sys.exit("pongoOS refuses new uploads. An earlier upload was cut off by a USB "
             "reset (cable moved, PC rebooted), and pongoOS can't recover from "
             "that. Hard-reboot the iPad (Power + Home), start pongoOS again with "
             "palera1n -p, and don't run another loader before this one.")


def upload(dev, data):
    start_upload(dev, len(data))
    for off in range(0, len(data), CHUNK):
        dev.write(2, data[off:off + CHUNK], 10000)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kernel", nargs="?", help="Linux.lzma (or an uncompressed arm64 Image)")
    ap.add_argument("dtbpack", nargs="?")
    ap.add_argument("-p", "--payload", help="shim payload for palera1n's pongoOS (bootr)")
    ap.add_argument("-c", "--cmdline", default=DEFAULT_CMDLINE, help="kernel command line (checkra1n route)")
    ap.add_argument("--touch-gen", type=int, choices=(1, 2),
                    help="touch report protocol for the kernel driver (default 2)")
    ap.add_argument("--no-touch-cal", action="store_true",
                    help="don't copy touch calibration from the Apple device tree")
    args = ap.parse_args()

    if args.payload:
        payload = open(args.payload, "rb").read()
        dev = find_pongo()
        if args.touch_gen:
            payload = bytearray(payload)
            struct.pack_into("<I", payload, 0xFF00 + 32, args.touch_gen)
            payload = bytes(payload)
        if not args.no_touch_cal:
            print("Reading touch calibration from the Apple device tree...")
            try:
                payload = add_overlay(payload, read_touch_cal(dev))
            except usb.core.USBError as e:
                print(f"  failed ({e}); booting without it")
        print(f"Loading payload ({len(payload) // (1024 * 1024)} MiB)...")
        upload(dev, payload)
        print("Booting...")
        try:
            command(dev, "bootr")
        except usb.core.USBError:
            pass  # the device drops off USB as the shim takes over
        print("Sent. A blue then green bar at the top of the screen means the shim ran.")
        return

    if not args.kernel or not args.dtbpack:
        ap.error("give --payload, or a kernel and a dtbpack")
    kernel = open(args.kernel, "rb").read()
    dtbpack = open(args.dtbpack, "rb").read()
    if dtbpack[:4] != b"Cows":
        sys.exit(f"{args.dtbpack}: not a dtbpack")

    dev = find_pongo()

    command(dev, f"linux_cmdline {args.cmdline}")

    print("Loading device tree pack...")
    upload(dev, dtbpack)
    command(dev, "fdt")

    print(f"Loading kernel ({len(kernel) // (1024 * 1024)} MiB)...")
    upload(dev, kernel)

    print("Booting...")
    try:
        command(dev, "bootl")
    except usb.core.USBError:
        pass  # the device drops off USB as Linux takes over
    print("Sent. Watch the iPad screen; USB ethernet appears after ~30 s.")


if __name__ == "__main__":
    main()
