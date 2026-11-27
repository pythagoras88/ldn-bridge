<#
Run ON WINDOWS: play with Ryujinx on Windows and the bridge in WSL, in one go (docs/WSL.md).

Attaches the USB adapter to WSL, loads its driver if it isn't loaded, starts the bridge in WSL (minimized window) and
windows\ldn_tunnel.py, then starts Ryujinx. Closing Ryujinx stops the bridge and removes the LDN Bridge adapter.
Asks for Administrator rights, because the adapter needs them.

    powershell -ExecutionPolicy Bypass -File play.ps1 -Ryujinx "E:\path\to\Ryujinx.exe" [-Game "E:\path\to\game.nsp"]
#>
param(
    [string]$Ryujinx = "",
    [string]$Game = "",
    [string]$Distro = "Ubuntu",
    [string]$HardwareId = "0e8d:7612"
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$($MyInvocation.MyCommand.Path)`"",
                 "-Ryujinx", "`"$Ryujinx`"", "-Game", "`"$Game`"", "-Distro", $Distro, "-HardwareId", $HardwareId)
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit
}

$Host.UI.RawUI.WindowTitle = "LDN Bridge + Ryujinx"

function Stop-WithMessage([string]$message) {
    Write-Host $message -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

function Step([string]$message) { Write-Host "-> $message" -ForegroundColor Cyan }

if (-not (Test-Path $Ryujinx)) { Stop-WithMessage "Ryujinx not found at '$Ryujinx'. Pass -Ryujinx with the path to Ryujinx.exe." }
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Stop-WithMessage "Python for Windows wasn't found. Install it, then try again." }
$usbipd = "C:\Program Files\usbipd-win\usbipd.exe"
if (-not (Test-Path $usbipd)) { $usbipd = "usbipd" }

# Keep WSL running while the adapter is attached and the driver loads. The bridge window keeps it running after that.
$keepAlive = Start-Process wsl -ArgumentList "-d $Distro --exec sleep 180" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
$wslHome = (wsl -d $Distro --exec printenv HOME | Out-String).Trim()
$project = "$wslHome/ldn-bridge"

Step "Stopping any bridge that's still running"
wsl -d $Distro --exec pkill -INT -f "wsl/bridge_windows.sh" | Out-Null
wsl -d $Distro --exec pkill -INT -f "ldn_bridge bridge switch-hosts" | Out-Null
Start-Sleep -Seconds 2

Step "Attaching the adapter to WSL"
$line = (& $usbipd list | Select-String -SimpleMatch $HardwareId | Select-Object -First 1)
if (-not $line) { Stop-WithMessage "The adapter ($HardwareId) isn't plugged in. Plug it in and try again." }
if ($line -match "Not shared") {
    & $usbipd bind --force --hardware-id $HardwareId
    Stop-WithMessage "The adapter wasn't set up for WSL yet, and now is. Unplug it, plug it back in, then run this again."
}
if ($line -notmatch "Attached") {
    & $usbipd attach --wsl --hardware-id $HardwareId
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Couldn't attach the adapter to WSL." }
    Start-Sleep -Seconds 3
}

wsl -d $Distro --exec bash "$project/wsl/adapter_ready.sh" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Step "Loading the adapter's driver (about 10 seconds)"
    wsl -d $Distro -u root --exec bash "$project/wsl/load_mt76.sh" | Select-String -Pattern "gave firmware|loaded mt76x2u|phy"
    wsl -d $Distro --exec bash "$project/wsl/adapter_ready.sh"
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "The driver didn't start. Unplug the adapter, plug it back in, then run this again."
    }
}

Step "Starting the bridge in WSL (minimized window)"
Start-Process wsl -ArgumentList "-d $Distro --cd $project --exec bash wsl/bridge_windows.sh" -WindowStyle Minimized

Step "Starting the Windows helper"
Start-Process $python -ArgumentList "`"$here\ldn_tunnel.py`" --exit-with $PID"

# Wait until the helper has made the adapter and pointed Ryujinx at it, before Ryujinx reads its settings.
$config = Join-Path $env:APPDATA "Ryujinx\Config.json"
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    $adapter = Get-NetAdapter -Name "LDN Bridge" -ErrorAction SilentlyContinue
    if ($adapter -and (Test-Path $config)) {
        $id = (Get-Content $config -Raw | ConvertFrom-Json).multiplayer_lan_interface_id
        if ($id -eq $adapter.InterfaceGuid) { $ready = $true; break }
    }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { Stop-WithMessage "The LDN Bridge adapter didn't come up. Check the helper window for errors." }
Stop-Process -Id $keepAlive.Id -ErrorAction SilentlyContinue

Step "Starting Ryujinx"
Write-Host ""
Write-Host "Host on the Switch, near the adapter. Before you open local multiplayer in the game, wait until the helper" -ForegroundColor Yellow
Write-Host "window says: Adapter 'LDN Bridge' set to 169.254.x.x" -ForegroundColor Yellow
Write-Host "Close Ryujinx to stop everything. Keep this window open until then." -ForegroundColor Yellow
if ($Game) {
    $emulator = Start-Process $Ryujinx -ArgumentList "`"$Game`"" -WorkingDirectory (Split-Path $Ryujinx) -PassThru
} else {
    $emulator = Start-Process $Ryujinx -WorkingDirectory (Split-Path $Ryujinx) -PassThru
}
$emulator.WaitForExit()

Step "Ryujinx closed. Stopping the bridge"
wsl -d $Distro --exec pkill -INT -f "wsl/bridge_windows.sh" | Out-Null
wsl -d $Distro --exec pkill -INT -f "ldn_bridge bridge switch-hosts" | Out-Null
# The helper notices this window closing and removes the adapter.
