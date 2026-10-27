#!/usr/bin/env bash
# One-click boot of Project Sandcastle Linux on an iPad 6 running iPadOS 15-17,
# from antiX (or any Debian-based Linux).
#
#   ./boot.sh               boot the iPad
#   ./boot.sh --launcher    put an "IpadCastle" icon on the desktop and exit
#   ./boot.sh --no-ssh      don't open the SSH session at the end
#   ./boot.sh --touch-gen=1 touch report protocol 1 (default 2)
#
# Steps: install python3-usb if needed -> fetch palera1n (checksum-pinned)
# -> palera1n puts the iPad into DFU and starts pongoOS -> upload
# out/ipadcastle.bin and "bootr" -> configure the USB network -> SSH in.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
payload="$here/out/ipadcastle.bin"
palera1n="$here/tools/bin/palera1n"
PALERA1N_VER=v2.4
IPAD_IP=172.16.1.1
HOST_IP=172.16.1.2

say()   { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
pause() { if [ -t 0 ]; then read -rp "Press Enter to close..." _ || true; fi; }
die()   { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; pause; exit 1; }

want_ssh=1
loader_args=()
for arg in "$@"; do
    case "$arg" in
        --no-ssh) want_ssh=0 ;;
        --touch-gen=[12]) loader_args+=(--touch-gen "${arg#*=}") ;;
        --launcher)
            desk="$HOME/Desktop"
            mkdir -p "$desk"
            cat > "$desk/IpadCastle.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=IpadCastle
Comment=Boot Linux on the iPad 6
Exec=x-terminal-emulator -e bash "$here/boot.sh"
Icon=computer
Terminal=false
EOF
            chmod +x "$desk/IpadCastle.desktop"
            echo "Created $desk/IpadCastle.desktop. Double-click it to boot the iPad."
            exit 0
            ;;
        *.zip) zip_arg="$arg" ;;
        *) die "unknown option: $arg" ;;
    esac
done

# --- root access -------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    SUDO=()
elif command -v sudo >/dev/null && sudo -v; then
    SUDO=(sudo)
else
    die "this needs root. Run it as:  su -c '$here/boot.sh'"
fi

# --- payload -----------------------------------------------------------------
if [ ! -f "$payload" ]; then
    say "Building out/ipadcastle.bin"
    zip="${zip_arg:-}"
    for z in "$here/linux-sandcastle.zip" "$HOME/Downloads/linux-sandcastle.zip"; do
        [ -z "$zip" ] && [ -f "$z" ] && zip="$z"
    done
    [ -n "$zip" ] && [ -f "$zip" ] || die "out/ipadcastle.bin is missing and linux-sandcastle.zip was not found.
Put linux-sandcastle.zip next to boot.sh or in ~/Downloads (or pass its path)."
    mkdir -p "$here/out"
    python3 - "$zip" "$here/out/Linux.lzma" <<'EOF'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    open(sys.argv[2], "wb").write(z.read("linux-sandcastle/Linux.lzma"))
EOF
    python3 "$here/tools/mkpayload.py" "$here/prebuilt/shim.bin" \
        "$here/prebuilt/J71b-palera1n.dtb" "$here/out/Linux.lzma" "$payload"
fi

# --- packages ----------------------------------------------------------------
if ! python3 -c 'import usb.core' 2>/dev/null; then
    say "Installing python3-usb and libusb"
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" apt-get install -y python3-usb libusb-1.0-0 usbmuxd
fi

# --- palera1n ----------------------------------------------------------------
if [ ! -x "$palera1n" ]; then
    case "$(uname -m)" in
        x86_64)        arch=x86_64 sha=ea531df933c0c8edab25ecb8f43faedd010177484482bb3744eaa4cf1cd48658 ;;
        i?86)          arch=x86    sha=c404cb01c6ca28334cdeaf76fd5e41d4d351d28fb826d5bc3b7c89dac2257aa5 ;;
        aarch64)       arch=arm64  sha=0ddcc3e703709f9cf9a85eb7c598f7500e2028fc4c60f3085eecb0b2bcbb138b ;;
        armv6l|armv7l) arch=armel  sha=7ffa9a80bd5bf2c07240023d18695446e37892fe7b2e65d0533993296bb29372 ;;
        *) die "no palera1n build for $(uname -m)" ;;
    esac
    say "Downloading palera1n $PALERA1N_VER ($arch)"
    url="https://github.com/palera1n/palera1n/releases/download/$PALERA1N_VER/palera1n-linux-$arch"
    mkdir -p "$(dirname "$palera1n")"
    tmp="$palera1n.part"
    if command -v curl >/dev/null; then curl -fL -o "$tmp" "$url"; else wget -O "$tmp" "$url"; fi
    echo "$sha  $tmp" | sha256sum -c --quiet || { rm -f "$tmp"; die "palera1n checksum mismatch"; }
    chmod +x "$tmp"
    mv "$tmp" "$palera1n"
fi

# --- iPad -> pongoOS ---------------------------------------------------------
pongo_present() {
    local d
    for d in /sys/bus/usb/devices/*; do
        [ "$(cat "$d/idVendor" 2>/dev/null)" = 05ac ] &&
        [ "$(cat "$d/idProduct" 2>/dev/null)" = 4141 ] && return 0
    done
    return 1
}

if pongo_present; then
    say "iPad is already in pongoOS"
else
    say "Starting pongoOS on the iPad"
    cat <<'EOF'
Connect the iPad with a USB-A to Lightning cable (USB-C adapters often fail).
palera1n will walk you through DFU mode. On the iPad 6:
  hold Power + Home ~4 s, then let go of Power and keep holding Home ~10 s.
The screen stays black in DFU mode. That is expected.
EOF
    "${SUDO[@]}" "$palera1n" -p || die "palera1n failed. Unplug, replug and run again."
    for _ in $(seq 30); do pongo_present && break; sleep 1; done
    pongo_present || die "pongoOS did not show up on USB"
fi

# --- boot Linux --------------------------------------------------------------
before="$(ls /sys/class/net)"
say "Sending Linux to the iPad"
"${SUDO[@]}" python3 "$here/tools/load-linux.py" --payload "$payload" "${loader_args[@]}"

say "Waiting for the iPad's USB network (up to 2 minutes)"
iface=""
for _ in $(seq 120); do
    for i in $(ls /sys/class/net); do
        grep -qx "$i" <<<"$before" || iface="$i"
    done
    [ -n "$iface" ] && break
    sleep 1
done
if [ -z "$iface" ]; then
    die "no USB network appeared. If the screen shows a green bar, Linux was started:
check the iPad's screen for kernel messages. A blue bar only means the shim got stuck."
fi
echo "iPad network interface: $iface"
# Ubuntu: keep NetworkManager from running DHCP on it and dropping our address
if command -v nmcli >/dev/null; then
    "${SUDO[@]}" nmcli device set "$iface" managed no 2>/dev/null || true
fi

up=0
for _ in $(seq 60); do
    # connman/dhcp clients on the host may strip the address; keep re-adding it
    ip -4 addr show dev "$iface" | grep -q "$HOST_IP/" ||
        "${SUDO[@]}" ip addr add "$HOST_IP/24" dev "$iface" 2>/dev/null || true
    "${SUDO[@]}" ip link set "$iface" up
    if ping -c1 -W1 "$IPAD_IP" >/dev/null 2>&1; then up=1; break; fi
    sleep 1
done
[ "$up" -eq 1 ] || die "the iPad does not answer at $IPAD_IP on $iface"

say "Linux is up on the iPad: ssh root@$IPAD_IP (password: alpine)"
if [ "$want_ssh" -eq 1 ] && command -v ssh >/dev/null; then
    # The iPad gets fresh host keys every boot, so don't pin them.
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "root@$IPAD_IP" || true
fi
pause
