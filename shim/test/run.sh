#!/usr/bin/env bash
# Run the shim on a real payload under qemu-aarch64 and check the result.
#   shim/test/run.sh out/ipadcastle.bin
# Needs: aarch64-linux-gnu-gcc, qemu-aarch64 (qemu-user), dtc.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
payload="$1"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

off=$(aarch64-linux-gnu-nm "$here/../shim.elf" | awk '$3 == "shim_main" { print "0x" $1 }')
aarch64-linux-gnu-gcc -static -O1 -o "$tmp/harness" "$here/harness.c"
out=$(qemu-aarch64 "$tmp/harness" "$payload" "$off" "$tmp/patched.dtb")
echo "$out"
fb=$(echo "$out" | sed -n 's/^fb=0x//p')
rd=$(echo "$out" | sed -n 's/^rd=//p')
rdend=$(echo "$out" | sed -n 's/^rdend=//p')
cells() { printf '<0x%02x 0x%02x>' "$((16#${1:0:8}))" "$((16#${1:8:8}))"; }
fbcells=$(printf '<0x%02x 0x%02x' "$((16#${fb:0:${#fb}-8}))" "$((16#${fb: -8}))")
gen=$(od -An -tu4 -j $((0xff00 + 32)) -N4 "$payload" | tr -d ' ')
[ "$gen" = 0 ] && gen=2

dtc -q -I dtb -O dts "$tmp/patched.dtb" > "$tmp/patched.dts"
fail=0
check() { if grep -qE "$1" "$tmp/patched.dts"; then echo "ok:   dtb has $2"; else echo "FAIL: dtb missing $2"; fail=1; fi; }
check 'reg = <0x08 0x00 0x00 0x7e000000>' "memory = physBase+memSize-DRAM base (0x7e000000)"
check "reg = $fbcells 0x00 0xc00000>" "framebuffer reg = fb, 12 MiB"
check 'width = <0x600>' "width 1536"
check 'height = <0x800>' "height 2048"
check 'stride = <0x1800>' "stride 6144"
check 'format = "x2r10g10b10"' "30-bit format"
check "generation = <0x0$gen>" "touch generation $gen (from the payload header)"
check 'compatible = "hx,touch"' "touch node present"
check "linux,initrd-start = $(cells "$rd")" "initrd-start ($rd)"
check "linux,initrd-end = $(cells "$rdend")" "initrd-end ($rdend)"
if grep -qiE '0x1ca5|ICFMT' "$tmp/patched.dts"; then echo "FAIL: placeholders left"; fail=1; else echo "ok:   no placeholders left"; fi
exit $fail
