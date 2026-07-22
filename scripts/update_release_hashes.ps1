$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root 'release'
$Output = Join-Path $ReleaseDir 'SHA256SUMS.txt'
$Version = (Get-Content -LiteralPath (Join-Path $Root 'firmware\version.json') -Raw |
    ConvertFrom-Json).version

$Artifacts = @(
    @{ Path = Join-Path $ReleaseDir 'VoxCortex\VoxCortex.exe'; Name = 'VoxCortex/VoxCortex.exe' }
    @{
        Path = Join-Path $ReleaseDir "VoxCortexFirmware-$Version-windows.zip"
        Name = "VoxCortexFirmware-$Version-windows.zip"
    }
    @{
        Path = Join-Path $ReleaseDir "VoxCortex-$Version-windows.zip"
        Name = "VoxCortex-$Version-windows.zip"
    }
)

$Checksums = foreach ($Artifact in $Artifacts) {
    if (Test-Path -LiteralPath $Artifact.Path) {
        $Hash = Get-FileHash -LiteralPath $Artifact.Path -Algorithm SHA256
        "$($Hash.Hash.ToLowerInvariant())  $($Artifact.Name)"
    }
}
$Checksums | Set-Content -LiteralPath $Output -Encoding ascii
Write-Host "Updated: $Output"
