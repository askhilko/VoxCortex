[CmdletBinding()]
param(
    [string]$Port,
    [switch]$Factory,
    [switch]$Force,
    [switch]$Yes,
    [string]$Manifest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Virtual environment not found. Run .\scripts\setup_windows.ps1 first.'
}
if (-not $Manifest) {
    $Manifest = Join-Path $Root 'release\firmware\manifest.json'
}
if (-not (Test-Path -LiteralPath $Manifest)) {
    throw 'Firmware manifest not found. Run .\scripts\build_firmware.ps1 first.'
}

$UpdaterArguments = @('-m', 'm5_dictation.firmware_updater', '--manifest', $Manifest)
if ($Port) { $UpdaterArguments += @('--port', $Port) }
if ($Factory) { $UpdaterArguments += '--factory' }
if ($Force) { $UpdaterArguments += '--force' }
if ($Yes) { $UpdaterArguments += '--yes' }
& $Python @UpdaterArguments
exit $LASTEXITCODE
