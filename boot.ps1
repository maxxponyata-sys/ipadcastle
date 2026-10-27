# One-click boot of Project Sandcastle Linux on an iPad 6 (iPadOS 15-17)
# from Windows. Double-click boot.cmd, or:
#
#   powershell -ExecutionPolicy Bypass -File boot.ps1             boot the iPad
#   powershell -ExecutionPolicy Bypass -File boot.ps1 -Launcher   desktop shortcut
#   powershell -ExecutionPolicy Bypass -File boot.ps1 -NoSsh      skip the SSH session
#
# palera1n has no Windows build, so the iPad must already be in pongoOS
# (palera1n -p from Linux, then move the cable; pongoOS lives in RAM and
# survives that). pongoOS needs the WinUSB or libusbK driver (Zadig).
#
# Steps: pyusb + libusb-1.0.dll -> upload out\ipadcastle-win.bin and "bootr"
# -> wait for the iPad's RNDIS network adapter -> 172.16.1.2/24 -> SSH in.
#   ... -TouchGen 1                                               touch report protocol 1
param([switch]$NoSsh, [switch]$Launcher, [ValidateSet(0, 1, 2)][int]$TouchGen = 0)

# Not 'Stop': in Windows PowerShell 5.1 that turns any stderr output of a
# native command (python, pip) into a terminating error, even with 2>$null.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSCommandPath
$payload = Join-Path $here 'out\ipadcastle-win.bin'
$IpadIp = '172.16.1.1'
$HostIp = '172.16.1.2'

function Say($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Pause-Close { Read-Host 'Press Enter to close' | Out-Null }
function Die($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; Pause-Close; exit 1 }
# Keep the window open on anything unexpected, so the error can be read.
trap { Die "$_`n$($_.InvocationInfo.PositionMessage)" }

if ($Launcher) {
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'IpadCastle.lnk'
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $here 'boot.cmd'
    $s.WorkingDirectory = $here
    $s.Save()
    Write-Host "Created $lnk. Double-click it to boot the iPad."
    exit 0
}

# --- administrator (needed to set the adapter's IP address) ------------------
$me = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($NoSsh) { $a += '-NoSsh' }
    if ($TouchGen) { $a += @('-TouchGen', "$TouchGen") }
    Start-Process powershell -Verb RunAs -ArgumentList $a
    exit 0
}

# --- python ------------------------------------------------------------------
$python = $null
$probe = 'import sys; print(sys.executable)'
# python on PATH first: "py -3" may pick a pre-release or free-threaded build
if (Get-Command python -ErrorAction SilentlyContinue) {
    $exe = & python -c $probe 2>$null
    if ($LASTEXITCODE -eq 0 -and $exe) { $python = "$exe".Trim() }
}
if (-not $python -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $exe = & py -3 -c $probe 2>$null
    if ($LASTEXITCODE -eq 0 -and $exe) { $python = "$exe".Trim() }
}
if (-not $python) { Die 'Python 3 was not found. Install it from https://www.python.org (tick "Add to PATH").' }

& $python -c 'import usb.core, libusb_package' 2>$null
if ($LASTEXITCODE -ne 0) {
    Say 'Installing pyusb and libusb'
    & $python -m pip install --user pyusb libusb-package
    if ($LASTEXITCODE -ne 0) { Die 'pip install pyusb libusb-package failed (no internet?)' }
}

# --- payload -----------------------------------------------------------------
if (-not (Test-Path $payload)) {
    Say 'Building out\ipadcastle-win.bin'
    $lzma = Join-Path $here 'out\Linux.lzma'
    if (-not (Test-Path $lzma)) {
        $zip = @((Join-Path $here 'linux-sandcastle.zip'),
                 (Join-Path $env:USERPROFILE 'Downloads\linux-sandcastle.zip')) |
               Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $zip) { Die 'out\Linux.lzma is missing and linux-sandcastle.zip was not found. Put it next to boot.ps1 or in Downloads.' }
        New-Item -ItemType Directory -Force (Join-Path $here 'out') | Out-Null
        & $python -c 'import sys, zipfile; open(sys.argv[2], "wb").write(zipfile.ZipFile(sys.argv[1]).read("linux-sandcastle/Linux.lzma"))' $zip $lzma
        if ($LASTEXITCODE -ne 0) { Die 'could not extract Linux.lzma' }
    }
    & $python (Join-Path $here 'tools\mkpayload.py') (Join-Path $here 'prebuilt\shim.bin') `
        (Join-Path $here 'prebuilt\J71b-palera1n.dtb') $lzma $payload --overlay (Join-Path $here 'overlay\rndis')
    if ($LASTEXITCODE -ne 0) { Die 'building the payload failed' }
}

# --- pongoOS -----------------------------------------------------------------
function Get-Pongo {
    Get-CimInstance Win32_PnPEntity -Filter "PNPDeviceID LIKE 'USB\\VID_05AC&PID_4141%'" |
        Where-Object { $_.Status -eq 'OK' -or $_.ConfigManagerErrorCode -eq 28 } | Select-Object -First 1
}

while (-not ($pongo = Get-Pongo)) {
    Write-Host @'

The iPad is not in pongoOS (USB 05AC:4141).
palera1n does not run on Windows. Start pongoOS from Linux (Ubuntu Live
or antiX): run "palera1n -p", follow its DFU steps, then plug the iPad
into this PC. pongoOS stays in the iPad's RAM until it is rebooted.
'@
    Read-Host 'Press Enter to check again (Ctrl+C to quit)' | Out-Null
}
if ($pongo.Service -notin @('WinUSB', 'libusbK')) {
    $drv = if ($pongo.Service) { $pongo.Service } else { 'none' }
    Die @"
pongoOS has no usable driver (current: $drv).
Run Zadig (https://zadig.akeo.ie), Options > List All Devices, pick
"PongoOS USB Device" (USB ID 05AC 4141), choose WinUSB and click
Install Driver. Then run boot.cmd again.
"@
}
Say "iPad is in pongoOS (driver: $($pongo.Service))"

# --- boot Linux --------------------------------------------------------------
$before = @(Get-NetAdapter -IncludeHidden | ForEach-Object { $_.InterfaceGuid })
Say 'Sending Linux to the iPad'
$loaderArgs = @((Join-Path $here 'tools\load-linux.py'), '--payload', $payload)
if ($TouchGen) { $loaderArgs += @('--touch-gen', "$TouchGen") }
& $python @loaderArgs
if ($LASTEXITCODE -ne 0) { Die 'loading Linux failed' }

Say "Waiting for the iPad's USB network (up to 2 minutes)"
$nic = $null
for ($i = 0; $i -lt 120 -and -not $nic; $i++) {
    $nic = Get-NetAdapter | Where-Object { $before -notcontains $_.InterfaceGuid } | Select-Object -First 1
    if (-not $nic) { Start-Sleep -Seconds 1 }
}
if (-not $nic) {
    Die @'
no USB network adapter appeared. If the iPad shows a green bar, Linux was
started: check its screen for kernel messages. A blue bar only means the
shim got stuck. In Device Manager, look for an unknown "iPad 6 Linux"
device and report what it shows.
'@
}
Write-Host "iPad network adapter: $($nic.Name) ($($nic.InterfaceDescription))"

$up = $false
for ($i = 0; $i -lt 60 -and -not $up; $i++) {
    $have = Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $HostIp }
    if (-not $have) {
        try {
            Set-NetIPInterface -InterfaceIndex $nic.ifIndex -Dhcp Disabled -ErrorAction SilentlyContinue
            Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
            New-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress $HostIp -PrefixLength 24 -ErrorAction Stop | Out-Null
        } catch { }
    }
    $up = Test-Connection -ComputerName $IpadIp -Count 1 -Quiet
    if (-not $up) { Start-Sleep -Seconds 1 }
}
if (-not $up) { Die "the iPad does not answer at $IpadIp on $($nic.Name)" }

Say "Linux is up on the iPad: ssh root@$IpadIp (password: alpine)"
if (-not $NoSsh -and (Get-Command ssh -ErrorAction SilentlyContinue)) {
    # The iPad gets fresh host keys every boot, so don't pin them.
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "root@$IpadIp"
}
Pause-Close
