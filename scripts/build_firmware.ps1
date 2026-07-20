$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
if (Test-Path -LiteralPath (Join-Path $Root '.venv\Scripts\pio.exe')) {
    & (Join-Path $Root '.venv\Scripts\pio.exe') run -d firmware
} else {
    pio run -d firmware
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
New-Item -ItemType Directory -Force release | Out-Null
& $Python (Join-Path $Root 'tools\package_firmware.py') `
    --root $Root `
    --build-dir (Join-Path $Root 'firmware\.pio\build\m5stack-stickc-plus2') `
    --output-dir (Join-Path $Root 'release\firmware')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$LegacyUpdater = Join-Path $Root 'release\firmware\M5FirmwareUpdater.exe'
if (Test-Path -LiteralPath $LegacyUpdater) {
    Remove-Item -LiteralPath $LegacyUpdater -Force
}
Copy-Item docs\USER_GUIDE.md release\firmware\README.md -Force
$Version = (Get-Content -LiteralPath (Join-Path $Root 'firmware\version.json') -Raw |
    ConvertFrom-Json).version
$Archive = Join-Path $Root "release\VoxCortexFirmware-$Version-windows.zip"
if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
Compress-Archive -Path (Join-Path $Root 'release\firmware\*') -DestinationPath $Archive -CompressionLevel Optimal
& (Join-Path $PSScriptRoot 'update_release_hashes.ps1')
Write-Host "Built: $Archive"
