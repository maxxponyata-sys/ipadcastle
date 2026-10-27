#!/usr/bin/env bash
# Build Project Sandcastle for the iPad 6.
#
#   ./build.sh /path/to/linux-sandcastle.zip
#
# Output in out/:
#   ipadcastle.bin  shim + iPad 6 tree + kernel, for palera1n (iPadOS 15-17)
#   ipadcastle-win.bin  the same with RNDIS USB networking, for boot.ps1
#   Linux.lzma      Corellium's kernel + built-in ramdisk, unchanged
#   dtbpack         original iPhone 7/7 Plus/iPod 7 trees + J71b + J72b,
#                   for checkra1n's Linux loader (older iOS)
# and refreshes prebuilt/ (shim.bin, J71b-palera1n.dtb), which boot.sh uses
# so the boot machine only needs python3.
#
# Needs: dtc, cpp, python3, unzip; aarch64-linux-gnu-gcc to rebuild the shim
# (otherwise prebuilt/shim.bin is used).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
zip="${1:-}"
out="$here/out"
work="$out/work"

if [ -z "$zip" ] || [ ! -f "$zip" ]; then
    echo "usage: $0 /path/to/linux-sandcastle.zip" >&2
    exit 1
fi

rm -rf "$work"
mkdir -p "$work/orig"
unzip -q -o -j "$zip" 'linux-sandcastle/Linux.lzma' 'linux-sandcastle/dtbpack' -d "$work"

compile() { # <src.dts> <out.dtb>
    cpp -nostdinc -undef -x assembler-with-cpp -P -I "$here/dts" "$1" -o "$2.pre"
    dtc -q -I dts -O dtb -o "$2" "$2.pre"
}

echo "== unpacking original dtbpack"
python3 "$here/tools/dtbpack.py" unpack "$work/dtbpack" "$work/orig" >/dev/null
python3 "$here/tools/dtbpack.py" list "$work/dtbpack"

echo "== checking SoC tree against Corellium's iPhone 7 (D10) tree"
compile "$here/dts/verify/D10-rebuild.dts" "$work/D10-rebuild.dtb"
python3 "$here/tools/dtcompare.py" "$work/orig/D10.dtb" "$work/D10-rebuild.dtb"

echo "== compiling iPad 6 trees"
entries=()
for f in "$work"/orig/*.dtb; do
    n="$(basename "$f" .dtb)"
    entries+=("$n=$f")
done
for board in J71b J72b; do
    compile "$here/dts/$board.dts" "$work/$board.dtb"
    entries+=("$board=$work/$board.dtb")
done

python3 "$here/tools/dtbpack.py" pack "$out/dtbpack" "${entries[@]}"
cp "$work/Linux.lzma" "$out/Linux.lzma"

echo "== building palera1n payload"
mkdir -p "$here/prebuilt"
if command -v aarch64-linux-gnu-gcc >/dev/null; then
    make -s -C "$here/shim"
    cp "$here/shim/shim.bin" "$here/prebuilt/shim.bin"
else
    echo "aarch64-linux-gnu-gcc not found, using prebuilt/shim.bin"
fi
compile "$here/dts/J71b-palera1n.dts" "$work/J71b-palera1n.dtb"
cp "$work/J71b-palera1n.dtb" "$here/prebuilt/J71b-palera1n.dtb"
# fastfetch for the ramdisk: the "polyfilled" build only needs glibc 2.17,
# the ramdisk has 2.30.
FF_URL=https://github.com/fastfetch-cli/fastfetch/releases/download/2.70.0/fastfetch-linux-aarch64-polyfilled.tar.gz
FF_SHA=6fc72549d097b3b1e2b35ef4677265da4cc23f07f253b5144d1662214cc14f37
ff="$work/overlay-fastfetch"
mkdir -p "$ff/usr/bin" "$work/ff"
curl -sfL -o "$work/ff.tgz" "$FF_URL"
echo "$FF_SHA  $work/ff.tgz" | sha256sum -c --quiet
tar xzf "$work/ff.tgz" -C "$work/ff"
cp "$work/ff/fastfetch-linux-aarch64-polyfilled/usr/bin/fastfetch" "$ff/usr/bin/fastfetch"

# Touch: ipad-touchd and its init script, plus Apple's iPad 6 touch firmware
# if out/adt/J71b.mtprops was fetched (see README, "Touchscreen").
touchfw="$work/overlay-touchfw"
mkdir -p "$touchfw"
if [ -f "$out/adt/J71b.mtprops" ]; then
    python3 "$here/tools/mtprops.py" export "$out/adt/J71b.mtprops" "$touchfw"
else
    echo "out/adt/J71b.mtprops not found: building without touch firmware"
fi
overlays=(--overlay "$ff" --overlay "$here/overlay/touch" --overlay "$touchfw")

python3 "$here/tools/mkpayload.py" "$here/prebuilt/shim.bin" "$here/prebuilt/J71b-palera1n.dtb" \
    "$out/Linux.lzma" "$out/ipadcastle.bin" "${overlays[@]}"
# Windows hosts: same, plus an overlay that switches USB networking to RNDIS.
python3 "$here/tools/mkpayload.py" "$here/prebuilt/shim.bin" "$here/prebuilt/J71b-palera1n.dtb" \
    "$out/Linux.lzma" "$out/ipadcastle-win.bin" --overlay "$here/overlay/rndis" "${overlays[@]}"
if command -v qemu-aarch64 >/dev/null && [ -f "$here/shim/shim.elf" ]; then
    "$here/shim/test/run.sh" "$out/ipadcastle.bin"
    "$here/shim/test/run.sh" "$out/ipadcastle-win.bin"
fi

# pongoOS copies the whole pack into a 256 KiB buffer (LINUX_DTREE_SIZE).
size=$(wc -c < "$out/dtbpack")
if [ "$size" -gt 262144 ]; then
    echo "error: dtbpack is $size bytes, pongoOS limit is 262144" >&2
    exit 1
fi
echo "== done: $out/ipadcastle.bin, $out/Linux.lzma, $out/dtbpack ($size bytes)"
