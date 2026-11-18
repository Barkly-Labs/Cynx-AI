[CmdletBinding()]
param(
    [string]$DeviceName,
    [string]$MacAddress
)

$ErrorActionPreference = 'Stop'
$CynxRoot = (Resolve-Path $PSScriptRoot).Path
$LocalData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }
$EnvironmentRoot = Join-Path $LocalData 'CYN-X\lepro-venv'
$LeproRepo = Join-Path $CynxRoot 'hardware\lepro'
$VendoredCli = Join-Path $LeproRepo 'lib\lepro\cli\ctl.py'
$OfficialUrl = 'https://github.com/lucavb/lepro-local.git'

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')" }
}

if ($env:OS -ne 'Windows_NT') { throw 'This setup script requires Windows PowerShell on Windows.' }
if (-not (Test-Path (Join-Path $CynxRoot 'main.py'))) { throw "CYN-X repository not found beside this script: $CynxRoot" }

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $Uv) { throw "uv is required. Install uv for your user, then rerun this script. No global Python packages were changed." }

$BasePython = $null
foreach ($Version in @('3.14','3.13')) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        $CandidatePython = & $PyLauncher.Source "-$Version" -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $CandidatePython) { $BasePython = [string]$CandidatePython; break }
    }
}
if (-not $BasePython) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $VersionText = & $PythonCommand.Source -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
        if ($LASTEXITCODE -eq 0 -and [version]$VersionText -ge [version]'3.13') { $BasePython = $PythonCommand.Source }
    }
}
if (-not $BasePython) { throw 'Python 3.13 or 3.14 is required for lepro-local. Install one side-by-side; this script will not replace your existing Python.' }

$ModulePrefix = 'hardware.lepro.lib.lepro.cli'
$CliRoot = $CynxRoot
if (-not (Test-Path $VendoredCli)) {
    $CloneAnswer = Read-Host 'The bundled lepro-local CLI source is missing. Clone the official repository into LocalAppData? (y/N)'
    if ($CloneAnswer -notmatch '(?i)^y(es)?$') { throw 'Setup stopped before cloning. You can rerun after providing the Lepro CLI source.' }
    $Git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $Git) { throw 'Git is required to clone lepro-local. Install Git for Windows and rerun.' }
    $CloneRoot = Join-Path $LocalData 'CYN-X\lepro-local'
    if (-not (Test-Path $CloneRoot)) { Invoke-Checked $Git.Source @('clone', $OfficialUrl, $CloneRoot) }
    $CliProject = Get-ChildItem -LiteralPath $CloneRoot -Filter pyproject.toml -Recurse | Where-Object {
        (Get-Content -Raw $_.FullName) -match 'lepro-ctl'
    } | Select-Object -First 1
    if (-not $CliProject) { throw 'The clone completed, but no lepro-ctl project was found.' }
    $CliRoot = $CliProject.Directory.FullName
    $ModulePrefix = 'lepro.cli'
}

$PythonExe = Join-Path $EnvironmentRoot 'Scripts\python.exe'
New-Item -ItemType Directory -Force -Path (Split-Path $EnvironmentRoot) | Out-Null
if (-not (Test-Path $PythonExe)) {
    Write-Info 'Creating an isolated Lepro virtual environment.'
    $VenvArgs = @('venv', '--python', $BasePython, $EnvironmentRoot)
    Invoke-Checked $Uv.Source $VenvArgs
} else {
    $ExistingVersion = & $PythonExe -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    if ($LASTEXITCODE -ne 0 -or [version]$ExistingVersion -lt [version]'3.13') {
        throw "Existing Lepro environment uses Python $ExistingVersion; preserve it and choose a separate Python 3.13+ environment before rerunning."
    }
    Write-Info "Reusing the existing Lepro environment at $EnvironmentRoot"
}

Write-Info 'Installing only the Lepro Bluetooth runtime dependencies in the isolated environment.'
Invoke-Checked $Uv.Source @('pip','install','--python',$PythonExe,'bleak>=3.0.2','pycryptodome>=3.23.0')

# Detect the current vendored packaging mismatch. Source execution below avoids
# building or silently editing this metadata.
$MetadataRoot = if ($ModulePrefix -eq 'hardware.lepro.lib.lepro.cli') { $LeproRepo } else { $CliRoot }
$PyProject = Get-Content -Raw (Join-Path $MetadataRoot 'pyproject.toml') -ErrorAction SilentlyContinue
$PackagingIssue = $false
if ($PyProject) {
    $ReadmeMatch = [regex]::Match($PyProject, '(?m)^readme\s*=\s*["'']([^"'']+)["'']')
    if ($ReadmeMatch.Success) {
        $ReadmePath = [IO.Path]::GetFullPath((Join-Path $MetadataRoot $ReadmeMatch.Groups[1].Value))
        if (-not (Test-Path $ReadmePath)) {
            $PackagingIssue = $true
            Write-Warn "Packaging metadata points to a missing README: $($ReadmeMatch.Groups[1].Value). The vendored package layout also differs from its wheel declaration."
            Write-Warn 'Safe local workaround: use the source module with this isolated dependency environment. No package metadata was changed.'
        }
    }
    $PackageMatch = [regex]::Match($PyProject, '(?ms)\[tool\.hatch\.build\.targets\.wheel\](.*?)(?=\r?\n\[|\z)')
    if ($PackageMatch.Success -and $PackageMatch.Groups[1].Value -match 'packages\s*=\s*\[\s*["'']([^"'']+)') {
        $WheelPackage = $Matches[1]
        if (-not (Test-Path (Join-Path $MetadataRoot $WheelPackage))) {
            $PackagingIssue = $true
            Write-Warn "Wheel metadata lists '$WheelPackage' but that directory is missing beneath the project root."
            Write-Warn 'Safe local workaround: use the source module with the isolated dependency environment; the script will not rewrite package metadata.'
        }
    }
}
if ($PackagingIssue) {
    $ContinueSourceMode = Read-Host 'Continue with the safe source-module workaround in the isolated environment, without editing package metadata? (Y/n)'
    if ($ContinueSourceMode -match '(?i)^n(o)?$') { throw 'Setup stopped before device pairing. Package metadata was not modified.' }
}

$BluetoothOk = $false
try {
    $BluetoothOk = @(Get-PnpDevice -Class Bluetooth -ErrorAction Stop | Where-Object { $_.Status -eq 'OK' }).Count -gt 0
} catch { }
if ($BluetoothOk) { Write-Info 'A Bluetooth adapter is enabled.' }
else { Write-Warn 'No enabled Bluetooth adapter was detected. Enable Bluetooth in Windows Settings or connect a supported BLE adapter, then rerun discovery. This script did not change Bluetooth settings.' }

$env:PYTHONPATH = $CynxRoot + $(if ($env:PYTHONPATH) { ';' + $env:PYTHONPATH } else { '' })
Push-Location $CynxRoot
try {
    & $PythonExe -m hardware.lepro.setup_cli configure $PythonExe $CliRoot $ModulePrefix
    if ($LASTEXITCODE -ne 0) { throw 'Could not save the local CLI environment configuration.' }
    foreach ($CliModule in @("${ModulePrefix}.ctl", "${ModulePrefix}.status", "${ModulePrefix}.bond")) {
        Write-Info "Checking actual CLI help: $CliModule --help"
        & $PythonExe -m $CliModule --help
        if ($LASTEXITCODE -ne 0) { throw "Lepro CLI help check failed for $CliModule. Check the Python environment and package layout." }
    }

    if (-not $MacAddress) {
        Write-Info 'Scanning for Lepro BLE devices using CYN-X discovery. The Lepro CLI itself has no discovery command.'
        $DiscoveryText = & $PythonExe -m hardware.lepro.setup_cli discover 2>$null
        $Discovered = @()
        if ($LASTEXITCODE -eq 0) {
            try { $Discovered = @((($DiscoveryText -join "`n") | ConvertFrom-Json).devices) } catch { }
        }
        if ($Discovered.Count -gt 0) {
            for ($Index = 0; $Index -lt $Discovered.Count; $Index++) {
                Write-Host "[$($Index + 1)] $($Discovered[$Index].name)  $($Discovered[$Index].mac)  bonded=$($Discovered[$Index].bonded)"
            }
            $Choice = Read-Host 'Choose a number, or press Enter to type a MAC address'
            if ($Choice -match '^\d+$' -and [int]$Choice -ge 1 -and [int]$Choice -le $Discovered.Count) {
                $MacAddress = [string]$Discovered[[int]$Choice - 1].mac
                if (-not $DeviceName) { $DeviceName = [string]$Discovered[[int]$Choice - 1].name }
            }
        }
        if (-not $MacAddress) { $MacAddress = Read-Host 'Enter the light MAC address (AA:BB:CC:DD:EE:FF)' }
    }
    if ($MacAddress -notmatch '(?i)^[0-9a-f]{2}(:[0-9a-f]{2}){5}$') { throw 'MAC address must use AA:BB:CC:DD:EE:FF format.' }
    if (-not $DeviceName) { $DeviceName = Read-Host 'Name this light (for example, Bedroom)' }
    if ([string]::IsNullOrWhiteSpace($DeviceName)) { throw 'A device name is required.' }
    $ModelConfirmation = Read-Host 'Confirm the device is a Lepro ZB1 RGB-IC string light (y/N)'
    if ($ModelConfirmation -notmatch '(?i)^y(es)?$') {
        throw 'This CLI has only verified Lepro ZB1 RGB-IC string lights. No device was enabled in CYN-X.'
    }

    Write-Info 'Bonding once if credentials do not already exist.'
    & $PythonExe -m hardware.lepro.setup_cli bond $MacAddress
    if ($LASTEXITCODE -ne 0) { throw 'Bonding failed. Existing credentials were preserved.' }

    Write-Info 'Checking the device with the real Lepro status CLI.'
    & $PythonExe -m hardware.lepro.setup_cli status $MacAddress
    if ($LASTEXITCODE -ne 0) { throw 'Status verification failed. Device configuration was not added.' }

    & $PythonExe -m hardware.lepro.setup_cli add $DeviceName $MacAddress ZB1
    if ($LASTEXITCODE -ne 0) { throw 'Could not save the selected device.' }

    Write-Host ''
    Write-Host 'Lepro setup complete.' -ForegroundColor Green
    Write-Host "Device: $DeviceName ($MacAddress)"
    Write-Host "Python: $PythonExe"
    Write-Host 'CYN-X will register the validated Lepro tools at startup.'
} finally { Pop-Location }
