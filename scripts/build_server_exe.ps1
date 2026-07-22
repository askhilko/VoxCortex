[CmdletBinding()]
param([switch]$SkipInstall)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$BuildRoot = Join-Path $Root '.build\server'
$Icon = Join-Path $BuildRoot 'VoxCortex.ico'
$DistRoot = Join-Path $Root 'release'
$AppDir = Join-Path $DistRoot 'VoxCortex'
$PreserveRoot = Join-Path $BuildRoot 'preserved-runtime'
$RuntimeItems = @('models', 'config.yaml', 'history.json', 'logs', 'tmp')
$FirmwareSource = Join-Path $DistRoot 'firmware'
$FirmwareManifest = Join-Path $FirmwareSource 'manifest.json'
$env:PYTHONPATH = Join-Path $Root 'pc_server\src'

$RootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
foreach ($ManagedPath in @($AppDir, $PreserveRoot)) {
    if (-not [IO.Path]::GetFullPath($ManagedPath).StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build path is outside the workspace: $ManagedPath"
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Virtual environment not found. Run .\scripts\setup_windows.ps1 first.'
}
if (-not (Test-Path -LiteralPath $FirmwareManifest)) {
    throw 'Firmware package not found. Run .\scripts\build_firmware.ps1 first.'
}

if (-not $SkipInstall) {
    & $Python -m pip install -c "$Root\pc_server\requirements-windows.lock" -e "$Root\pc_server[speech,firmware,build]"
    if ($LASTEXITCODE -ne 0) { throw 'Could not install EXE build dependencies.' }
}

& $Python -m voxcortex.icons --output $Icon
if ($LASTEXITCODE -ne 0) { throw 'Could not create application icon.' }

$Arguments = @(
    '--noconfirm',
    '--clean',
    '--onedir',
    '--windowed',
    '--noupx',
    '--name', 'VoxCortex',
    '--icon', $Icon,
    '--paths', "$Root\pc_server\src",
    '--distpath', $DistRoot,
    '--workpath', "$BuildRoot\work",
    '--specpath', $BuildRoot,
    '--exclude-module', 'pytest',
    '--exclude-module', 'pyautogui',
    '--exclude-module', 'mouseinfo',
    '--hidden-import', 'faster_whisper',
    '--hidden-import', 'pyperclip',
    '--hidden-import', 'serial',
    '--hidden-import', 'serial.tools.list_ports',
    '--hidden-import', 'serial.tools.list_ports_windows',
    '--collect-all', 'esptool',
    '--collect-all', 'faster_whisper',
    '--collect-all', 'ctranslate2',
    '--collect-all', 'av',
    '--collect-all', 'tokenizers',
    '--collect-all', 'huggingface_hub',
    "$Root\pc_server\tray_entry.py"
)
if (Test-Path -LiteralPath $PreserveRoot) {
    throw "Previous preserved runtime data must be restored first: $PreserveRoot"
}
New-Item -ItemType Directory -Path $PreserveRoot | Out-Null
foreach ($Item in $RuntimeItems) {
    $Source = Join-Path $AppDir $Item
    if (Test-Path -LiteralPath $Source) {
        Move-Item -LiteralPath $Source -Destination (Join-Path $PreserveRoot $Item)
    }
}

try {
    & $Python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
}
finally {
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    foreach ($Item in $RuntimeItems) {
        $Preserved = Join-Path $PreserveRoot $Item
        if (Test-Path -LiteralPath $Preserved) {
            Move-Item -LiteralPath $Preserved -Destination (Join-Path $AppDir $Item)
        }
    }
    if (Test-Path -LiteralPath $PreserveRoot) {
        Remove-Item -LiteralPath $PreserveRoot -Force
    }
}

# PyInstaller can resolve the base and auxiliary Visual C++ runtime DLLs from
# different redistributable versions. CTranslate2 then crashes while creating
# a model. Keep the four runtime files from the same installed x64 runtime.
$InternalDir = Join-Path $AppDir '_internal'
foreach ($RuntimeDll in @('msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    $RuntimeSource = Join-Path $env:WINDIR "System32\$RuntimeDll"
    if (-not (Test-Path -LiteralPath $RuntimeSource)) {
        throw "Microsoft Visual C++ runtime file not found: $RuntimeSource"
    }
    Copy-Item -LiteralPath $RuntimeSource -Destination (Join-Path $InternalDir $RuntimeDll) -Force
}

$TargetConfig = Join-Path $AppDir 'config.example.yaml'
$SourceConfig = Join-Path $Root 'pc_server\config.example.yaml'
Copy-Item -LiteralPath $SourceConfig -Destination $TargetConfig -Force
Copy-Item -LiteralPath (Join-Path $Root 'docs\USER_GUIDE.md') -Destination (Join-Path $AppDir 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $Root 'LICENSE') -Destination (Join-Path $AppDir 'LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $Root 'THIRD_PARTY_NOTICES.md') `
    -Destination (Join-Path $AppDir 'THIRD_PARTY_NOTICES.md') -Force

$FirmwareTarget = Join-Path $AppDir 'firmware'
New-Item -ItemType Directory -Force -Path $FirmwareTarget | Out-Null
Get-ChildItem -LiteralPath $FirmwareSource -File |
    Where-Object { $_.Name -ne 'M5FirmwareUpdater.exe' } |
    Copy-Item -Destination $FirmwareTarget -Force

$Exe = Join-Path $AppDir 'VoxCortex.exe'
$Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Exe
Write-Host "Built: $Exe"
Write-Host "SHA256: $($Hash.Hash.ToLowerInvariant())"
& (Join-Path $PSScriptRoot 'update_release_hashes.ps1')
