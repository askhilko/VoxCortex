$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root 'release'
$Output = Join-Path $ReleaseDir 'SHA256SUMS.txt'

$Artifacts = @(
    @{ Path = Join-Path $ReleaseDir 'M5AIDictationServer\M5AIDictationServer.exe'; Name = 'M5AIDictationServer/M5AIDictationServer.exe' }
)
$FirmwareArchives = Get-ChildItem -LiteralPath $ReleaseDir -Filter 'M5AIDictationFirmware-*-windows.zip' -File -ErrorAction SilentlyContinue
foreach ($Archive in $FirmwareArchives) {
    $Artifacts += @{ Path = $Archive.FullName; Name = $Archive.Name }
}
$ApplicationArchives = Get-ChildItem -LiteralPath $ReleaseDir -Filter 'M5AIDictationServer-*-windows.zip' -File -ErrorAction SilentlyContinue
foreach ($Archive in $ApplicationArchives) {
    $Artifacts += @{ Path = $Archive.FullName; Name = $Archive.Name }
}

$Checksums = foreach ($Artifact in $Artifacts) {
    if (Test-Path -LiteralPath $Artifact.Path) {
        $Hash = Get-FileHash -LiteralPath $Artifact.Path -Algorithm SHA256
        "$($Hash.Hash.ToLowerInvariant())  $($Artifact.Name)"
    }
}
$Checksums | Set-Content -LiteralPath $Output -Encoding ascii
Write-Host "Updated: $Output"
