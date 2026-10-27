# IpadCastle: Project Sandcastle on the iPad 6

This port runs Corellium's Project Sandcastle Linux build on the iPad 6:

- J71b: iPad7,5, Wi-Fi
- J72b: iPad7,6, Cellular

The iPad 6 uses the same A10 (T8010) chip as the iPhone 7. Corellium's prebuilt kernel (`Linux.lzma`, Linux 5.4.14-crlm with a built-in ramdisk) already has every SoC driver. This project adds what was missing: an iPad 6 device tree, plus a way to boot on iPadOS 15–17.

An iPad 6 on iPadOS 17 has booted this build through the palera1n route from Windows (`boot.cmd`), with SSH over USB working. Read the "Status" section below before you try it.

## One-click boot from antiX (iPadOS 15–17)

1. Copy the whole `IpadCastle` folder into your home folder on the antiX PC. Run it from there, not from the USB stick.
2. In a terminal inside the folder, create the desktop icon (only needed once):
   ```bash
   bash boot.sh --launcher
   ```
3. Plug the iPad in with a **USB-A to Lightning** cable, then double-click **IpadCastle** on the desktop. You can also run `bash boot.sh` instead.

The script does the rest:

| Step | What happens |
|---|---|
| Packages | Installs `python3-usb`, `libusb-1.0-0` and `usbmuxd` with apt if they're missing (first run only) |
| palera1n | Downloads palera1n v2.4 for your CPU (64-bit or 32-bit antiX) and checks its SHA-256 |
| DFU and pongoOS | palera1n walks you through DFU mode, then starts pongoOS on the iPad |
| Boot | Uploads `out/ipadcastle.bin` and boots it |
| Network | Waits for the iPad's USB network and gives your PC the address `172.16.1.2` |
| SSH | Opens `ssh root@172.16.1.1`. The password is `alpine`. |

To put the iPad 6 into DFU mode: hold Power + Home for about 4 seconds, then let go of Power and keep holding Home for about 10 seconds. The screen stays black.

You need root. If `sudo` isn't set up for your user, run `su -c 'bash boot.sh'` instead.

Nothing is written to the iPad's storage. A hard reboot (hold Power + Home) brings back iPadOS.

### Reading the bars on the iPad screen

| What you see | Meaning |
|---|---|
| Blue bar at the top | The shim started |
| Green bar | The kernel was set up and Linux is being started |
| Blue bar only | The shim got stuck |
| Green bar, then nothing | The kernel isn't coming up. Note what's on screen and report it. |

## Запуск с Ubuntu Live (LiveCD / LiveUSB)

1. Загрузитесь в Ubuntu Live («Try Ubuntu») и подключитесь к интернету. Скрипт скачивает palera1n и пакет `python3-usb`.
2. Скопируйте всю папку `IpadCastle` в домашнюю папку (`~`), с флешки или с диска Windows. Не запускайте её прямо с NTFS-диска или флешки: там файлы могут быть неисполняемыми.
3. Включите репозиторий universe. В Live-сессии он часто выключен, а `python3-usb` лежит в нём:
   ```bash
   sudo add-apt-repository -y universe
   ```
4. Перейдите в папку:
   ```bash
   cd ~/IpadCastle
   ```
5. Запустите загрузку:
   ```bash
   bash boot.sh
   ```

В Live-сессии `sudo` работает без пароля, SSH-клиент уже установлен. Скрипт сам отключает NetworkManager для USB-сети iPad, чтобы тот не сбрасывал адрес `172.16.1.2`.

Советы:
- Подключайте iPad кабелем **USB-A → Lightning** напрямую в порт на задней панели ПК, без хабов и переходников.
- Если iPad остался в pongoOS после прошлой попытки, сделайте жёсткую перезагрузку (Power + Home) и запустите `bash boot.sh` заново.
- DFU на iPad 6: держите Power + Home около 4 секунд, затем отпустите Power и держите Home ещё около 10 секунд. Экран остаётся чёрным.

Если появляется ошибка `USBError: [Errno 5] Input/Output Error` или iPad не отвечает, сохраните вывод этих команд:
```bash
lsusb | grep -i 05ac
```
```bash
sudo dmesg | tail -30
```

## Запуск с Windows

Нужны Windows 10/11, Python 3 с [python.org](https://www.python.org) (при установке отметьте «Add to PATH») и интернет при первом запуске.

1. **Введите iPad в pongoOS.** Для Windows palera1n не существует, поэтому сделайте это из Linux (Ubuntu Live или antiX):
   ```bash
   sudo palera1n -p
   ```
   Если `boot.sh` уже запускался, palera1n лежит в `tools/bin/palera1n`. Когда на экране iPad появится pongoOS, переключите кабель в ПК с Windows (или перезагрузите ПК в Windows). pongoOS живёт в оперативной памяти iPad и переживает отключение кабеля, но не перезагрузку iPad.

   **Важно:** после `palera1n -p` не запускайте на Linux `boot.sh` и `load-linux.py`. Если загрузку прервать сбросом USB (переключением кабеля или перезагрузкой ПК), pongoOS перестаёт принимать новые загрузки до перезагрузки iPad. Тогда загрузчик пишет «pongoOS refuses new uploads»: перезагрузите iPad (Power + Home) и снова выполните `palera1n -p`.
2. **Поставьте драйвер для pongoOS (один раз).** Откройте [Zadig](https://zadig.akeo.ie), включите Options → List All Devices и выберите **PongoOS USB Device** (USB ID `05AC 4141`). Выберите **WinUSB** (libusbK тоже подойдёт) и нажмите Install Driver.
3. **Запустите двойным щелчком `boot.cmd`.** Скрипт попросит права администратора: без них нельзя задать IP-адрес сетевому адаптеру. Ярлык на рабочем столе можно создать так:
   ```bat
   powershell -ExecutionPolicy Bypass -File boot.ps1 -Launcher
   ```

Что делает `boot.ps1`:

| Шаг | Что происходит |
|---|---|
| Python | Ставит `pyusb` и `libusb-package` (в нём `libusb-1.0.dll`) через `pip --user`, если их ещё нет |
| Проверка | Убеждается, что iPad в pongoOS и у него драйвер WinUSB или libusbK |
| Загрузка | Отправляет `out\ipadcastle-win.bin` и командой `bootr` запускает его |
| Сеть | Ждёт сетевой адаптер iPad и назначает ему адрес `172.16.1.2/24` |
| SSH | Открывает `ssh root@172.16.1.1`, пароль `alpine` |

### Почему для Windows отдельный файл

Ramdisk Sandcastle поднимает USB-сеть в режиме CDC ECM, а для ECM в Windows драйвера нет. В `out\ipadcastle-win.bin` то же ядро и то же дерево устройств, но к ним добавлен маленький оверлей ramdisk: [overlay/rndis/etc/network/usb0-up](overlay/rndis/etc/network/usb0-up). Ядро распаковывает его поверх встроенного ramdisk, и iPad включает сеть в режиме RNDIS с дескрипторами Microsoft OS. Под такое устройство Windows сама ставит встроенный драйвер RNDIS. Интерфейс на iPad по-прежнему называется `usb0` с адресом `172.16.1.1`. Обычный `out/ipadcastle.bin` (для Linux) остаётся на ECM.

Если сетевой адаптер не появился, а на iPad видна зелёная полоса, откройте Диспетчер устройств и посмотрите, что показано для устройства **iPad 6 Linux**.

## Why there's a shim

On iPadOS 15–17, checkra1n can't patch iBoot, so palera1n is needed. palera1n's pongoOS fork removed the Linux loader that Sandcastle used (the `fdt` and `bootl` commands). It still has `bootr`, which jumps to a raw image with iBoot's `boot_args`, the record of RAM and screen details.

[shim/](shim/) is an 856-byte first stage that runs at that point. It does three things:
- **Device tree:** it fills in the exact RAM size and the framebuffer address, size, stride and pixel format from `boot_args`, in place of placeholder values in [J71b-palera1n.dts](dts/J71b-palera1n.dts). It also points `linux,initrd-start`/`-end` at the optional ramdisk overlay in the payload (the Windows payload carries one; otherwise both are 0).
- **Kernel:** it moves the kernel up to a 2 MiB-aligned address.
- **Jump:** it starts the kernel the way Linux expects (`x0` = DTB, MMU off).

[shim/test/](shim/test/) runs the real shim binary on the real payload under `qemu-aarch64`, using a fake iPad 6 `boot_args`, and checks the result. `build.sh` runs this test automatically.

## What's here

| Path | Purpose |
|---|---|
| `boot.sh` | The one-click boot script for antiX |
| `boot.cmd`, `boot.ps1` | The one-click boot script for Windows |
| `out/ipadcastle.bin` | Ready-to-boot payload: shim, iPad 6 tree and kernel |
| `out/ipadcastle-win.bin` | The same plus the RNDIS overlay, for Windows |
| `overlay/rndis/` | Ramdisk overlay that switches USB networking to RNDIS |
| `overlay/touch/` | Touch firmware loader `ipad-touchd` and its init script |
| `tests/` | Offline tests for the touch loader and the pongoOS `dt` parser |
| `prebuilt/` | Shim and device tree binaries, so `boot.sh` only needs Python |
| `dts/t8010-sandcastle.dtsi` | A10 SoC description, rebuilt as readable source from Corellium's iPhone 7 tree |
| `dts/ipad6.dtsi`, `J71b.dts`, `J72b.dts`, `J71b-palera1n.dts` | iPad 6 board files |
| `dts/verify/D10-rebuild.dts` | iPhone 7 rebuilt on the SoC file. The build checks it matches Corellium's original. |
| `shim/` | The first-stage loader for palera1n, and its QEMU test |
| `tools/` | dtbpack packer, DTB comparer, payload builder, USB loader |
| `build.sh` | Rebuilds everything from `linux-sandcastle.zip` |

## Rebuilding

Rebuild on Linux or WSL. It needs `dtc`, `cpp`, `python3` and `unzip`. Two more are optional: `aarch64-linux-gnu-gcc` (to rebuild the shim) and `qemu-user` (to run its test).

```bash
./build.sh ~/Downloads/linux-sandcastle.zip
```

## Older iOS (checkra1n)

On iOS versions that checkra1n supports, checkra1n's own pongoOS can load Linux directly:

```bash
sudo checkra1n -cp
```

```bash
sudo python3 tools/load-linux.py out/Linux.lzma out/dtbpack
```

## Status

**Expected to work.** These parts are the same on every A10 device, and the iPad 6 tree uses the iPhone 7 definitions unchanged:
- CPU cores and frequency scaling
- Interrupt controller, GPIO and UARTs
- USB ethernet gadget and SSH
- Watchdog reboot
- Home, power and volume buttons. Their GPIO numbers come from the mainline Linux iPad 6 tree.
- Screen output. iBoot leaves the panel and backlight on, and the kernel draws to it as a simple framebuffer.

**Experimental: touchscreen.** Enabled from the iPad's own Apple device tree; see "Touchscreen" below. Not yet run on hardware.

**Disabled on purpose.** The wiring for these parts on the iPad 6 isn't known. Driving the wrong PMIC rail or GPIO could do damage, so they stay off:
- Battery gauge and charger
- PMU (no RTC, and `poweroff` won't work; `reboot` still does)
- Wi-Fi, Bluetooth and NVMe storage

The root filesystem is the ramdisk built into the kernel.

**Tested on hardware** (iPad 6, iPadOS 17, pongoOS from palera1n `-p`, then Windows with WinUSB):
- The shim boots the kernel through `bootr`, and X comes up on the screen.
- The RNDIS overlay works: Windows binds its own RNDIS driver, and `ssh root@172.16.1.1` logs in.

**Untested.**
- Booting from Linux with `boot.sh` (ECM networking) hasn't been completed on hardware.
- On the palera1n route, the screen uses iBoot's native pixel format. It's 30-bit on A10, so the kernel gets `x2r10g10b10`. checkra1n instead switched the display to 32-bit, so the X desktop may look different or fail to start. The console and SSH don't depend on this.
- On the checkra1n route, the 128 MiB reserved at the top of RAM is an estimate.

`fastfetch` is included in both payloads (the glibc-2.17 "polyfilled" release, pinned by SHA-256 in `build.sh`). Run `fastfetch` over SSH.

## Touchscreen

### Как проверить

Тачскрин включается сам при загрузке через `boot.cmd`. Сначала загрузчик на ПК читает калибровку из pongoOS. После загрузки Linux демон `ipad-touchd` загружает прошивку в тач-контроллер. Проверьте по SSH:

```bash
cat /var/log/ipad-touchd.log
```

- **«controller is up»** — прошивка загружена. Потрогайте экран: если курсор X двигается, всё работает.
- **«reports need generation 1»** (или 2) — контроллер жив, но драйверу ядра нужен другой протокол чтения. Загрузите заново с `boot.cmd -TouchGen 1` (или `2`).
- **Что-то другое** — пришлите весь лог. Каждая строка показывает, на каком шаге контроллер перестал отвечать.

Если контроллер поднялся, а касания не доходят, посмотрите сырые пакеты:

```bash
/etc/init.d/S30hx-touchd stop; ipad-touchd --dump
```

Перезапуск демона по SSH (`/etc/init.d/S30hx-touchd restart`) заново загружает прошивку, перезагружать iPad не нужно. Новую версию `ipad-touchd` можно залить на работающий iPad с Windows командой `tools\push-touchd.cmd` (пароль `alpine`): она перезапустит демон и покажет его журнал. Ключи для опытов: `-v` (каждый обмен по SPI), `--cal-format z2`, `--zero-cal`, `--mt-type 1|2`.

### How it works

| Piece | What it does |
|---|---|
| `dts/ipad6.dtsi` | `hx,touch` on spi3 with the pins below and the touch clock at 24 MHz. No supplies: the Sandcastle kernel has no `regulator-fixed` driver (a first try left the driver deferred forever), so the driver gets dummy regulators. |
| `tools/load-linux.py` | Before uploading Linux, reads `multi-touch-calibration`, `multitouch-to-display-offset`, `firefly-calibration` and `pressure-effect-correction` from the live Apple device tree with pongoOS `dt` (iBoot fills them from syscfg), and appends them to the ramdisk overlay as `/etc/hw/touch-cal/*.bin`. `--touch-gen` sets the kernel driver's report protocol through the shim. |
| `overlay/touch/usr/bin/ipad-touchd` | Python 2 firmware loader that replaces Corellium's `hx-touchd`. It switches on the two power GPIOs through `/sys/class/gpio` (power_ana 0x91, then power_ldo 0x1d), then follows `hx-touchd`'s boot ROM handshake, sends the firmware blob, builds calibration load packets in the K1HBPP14 layout and runs the boot sequence from the firmware config, reads metrics from report 0xD9 (trying both read styles), then hands over to the kernel driver. |
| `overlay/touch/etc/init.d/S30hx-touchd` | Starts it at boot and points `xorg.conf` at the touch input device. |
| Touch input | The iPad firmware's frames (`90 03 …`, touch count at byte 26, 48-byte records from byte 36 with float32 x/y in micrometres) aren't the iPhone layout the `hx-touch` driver parses, and the kernel has no `uinput`. So by default `ipad-touchd` reads the frames itself and moves the X pointer through XTest (first finger, finger down = button 1). `--kernel` keeps the old hand-over; `--calib` logs raw coordinates; `--swap-xy` and `--flip-x` fix orientation; Y is mirrored by default (the panel counts from the bottom edge, checked on hardware), `--no-flip-y` turns that off. |
| `tests/touchd_test.py` | Rebuilds Apple's iPad, iPhone 7 and iPod 7 firmware blobs byte for byte with the loader's packet code, checks register-write packets against Corellium's C, and runs the whole boot flow against a fake controller, on Python 3 and on the ramdisk's Python 2.7 under QEMU. `tests/dtparse_test.py` checks the pongoOS `dt` parser. |

The firmware is Apple's and isn't in this repository. `build.sh` adds it when `out/adt/J71b.mtprops` exists. To fetch it (needs `pip install libfsapfs-python pyliblzfse`):

```bash
python tools/ipswfs.py https://updates.cdn-apple.com/2025SpringFCS/fullrestores/122-77020/D8DBC7A6-00AE-468D-8580-7FE5656EAE45/iPad_64bit_TouchID_ASTC_17.7.11_21H461_Restore.ipsw 044-75473-038.dmg /usr/share/firmware/multitouch/J71b.mtprops out/adt/J71b.mtprops
```

### What is known

From `DeviceTree.j71bap.im4p` (iPadOS 17.7.11), compared with the iPhone 7 tree that Corellium's working `hx,touch` node came from. Use `tools/ipswget.py` and `tools/adtdump.py` to fetch and read it.

| | iPhone 7 (D10) | iPad 6 (J71b) |
|---|---|---|
| Bus | spi2 | spi3 |
| reset / CS / IRQ GPIO | 0xa1 / 0x51 / 0xa6 | 0x1f / 0x55 / 0x15 |
| Power | PMU LDO and switch (I2C) | GPIO 0x1d (`power_ldo`), GPIO 0x91 (`power_ana`) |
| Touch clock | 32768 Hz | 24 MHz |
| Firmware personality | C1F5D,2 | K1F19,4 |
| Transport | `hid-transport,k1`, HBPP 1.3 | `hid-transport,spi`, HBPP 1.4 |

The firmware, `J71b.mtprops`, holds one `Constructed Firmware` blob (`J71B-GrapeFW-0x0747.bin`): a single load packet to 0x100000. The packet layout matches the iPhone 7's except for an extra zero word before the checksum, which is what "K1HBPP14" means here. The firmware config gives the calibration targets (0x100400, 0x102a00, 0x101400, 0x102e00) and a boot sequence of four register writes, ending with a toggle of bit 0 at 0x400b0000. Corellium's `hx-touchd` either expects a list of blobs (iPhone 7) or hard-codes iPod 7 addresses for single blobs, so it can't boot this controller.

Unknowns that the first run will settle, all logged by `ipad-touchd`:
- Whether the boot ROM handshake and prelude (`1AA1 18E1`, as on iPhone 7) are right for this controller.
- Whether calibration packets need the K1HBPP14 layout (default) or the Z2 one (`--cal-format z2`).
- Whether iBoot fills the calibration properties (the loader prints what it found).
- Which report protocol the kernel driver needs (detected and reported).
- How touch coordinates map onto the portrait screen.

## Enabling more hardware

Each block needs a value read from the iPad's own Apple device tree. Look up the GPIO and PMU addresses for that block and add the nodes to `dts/ipad6.dtsi`. `dts/verify/D10-rebuild.dts` shows the iPhone 7 versions of every board node to use as a template.

## License

GPL-2.0, see `LICENSE`. The repository holds no Apple or Corellium binaries: `build.sh` downloads Corellium's Sandcastle kernel and reads the touch firmware out of Apple's IPSW at build time, into `out/`, which is not committed.
