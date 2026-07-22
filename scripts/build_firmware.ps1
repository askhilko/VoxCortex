$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
$Pio = Join-Path $Root '.venv\Scripts\pio.exe'
if (-not (Test-Path -LiteralPath $Pio)) {
    $Pio = (Get-Command pio -ErrorAction Stop).Source
}
& $Pio run -d firmware
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Pio run -d firmware -t idedata | Out-Null
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
Copy-Item LICENSE release\firmware\LICENSE.txt -Force
Copy-Item THIRD_PARTY_NOTICES.md release\firmware\THIRD_PARTY_NOTICES.md -Force
$FirmwareLicenses = Join-Path $Root 'release\firmware\THIRD_PARTY_LICENSES\firmware'
New-Item -ItemType Directory -Path $FirmwareLicenses -Force | Out-Null
$FirmwareLicenseSources = @(
    @{ Name = 'ArduinoJson-7.4.2-LICENSE.txt'; Path = 'firmware\.pio\libdeps\m5stack-stickc-plus2\ArduinoJson\LICENSE.txt' },
    @{ Name = 'M5GFX-0.2.15-LICENSE.txt'; Path = 'firmware\.pio\libdeps\m5stack-stickc-plus2\M5GFX\LICENSE' },
    @{ Name = 'M5Unified-0.2.10-LICENSE.txt'; Path = 'firmware\.pio\libdeps\m5stack-stickc-plus2\M5Unified\LICENSE' },
    @{ Name = 'ArduinoWebSockets-2.6.1-LICENSE.txt'; Path = 'firmware\.pio\libdeps\m5stack-stickc-plus2\WebSockets\LICENSE' }
)
foreach ($LicenseSource in $FirmwareLicenseSources) {
    $Source = Join-Path $Root $LicenseSource.Path
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Firmware dependency license not found: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $FirmwareLicenses $LicenseSource.Name) -Force
}
$Version = (Get-Content -LiteralPath (Join-Path $Root 'firmware\version.json') -Raw |
    ConvertFrom-Json).version
$Archive = Join-Path $Root "release\VoxCortexFirmware-$Version-windows.zip"
if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
Compress-Archive -Path (Join-Path $Root 'release\firmware\*') -DestinationPath $Archive -CompressionLevel Optimal
& (Join-Path $PSScriptRoot 'update_release_hashes.ps1')
Write-Host "Built: $Archive"
