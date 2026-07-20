[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root 'release'
$AppDir = Join-Path $ReleaseDir 'M5AIDictationServer'
$StageRoot = Join-Path $Root '.build\release-package'
$StageApp = Join-Path $StageRoot 'M5AIDictationServer'
$Version = (Get-Content -LiteralPath (Join-Path $Root 'firmware\version.json') -Raw |
    ConvertFrom-Json).version
$Archive = Join-Path $ReleaseDir "M5AIDictationServer-$Version-windows.zip"
$ExcludedRuntimeItems = @('models', 'history.json', 'logs', 'tmp', 'config.yaml')

$RootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
$StageFull = [IO.Path]::GetFullPath($StageRoot)
if (-not $StageFull.StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe release staging path: $StageFull"
}
if (-not (Test-Path -LiteralPath (Join-Path $AppDir 'M5AIDictationServer.exe'))) {
    throw 'Windows application not found. Run .\scripts\build_server_exe.ps1 first.'
}

if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StageApp -Force | Out-Null

Get-ChildItem -LiteralPath $AppDir -Force |
    Where-Object { $_.Name -notin $ExcludedRuntimeItems } |
    Copy-Item -Destination $StageApp -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Root 'pc_server\config.example.yaml') `
    -Destination (Join-Path $StageApp 'config.yaml') -Force
Copy-Item -LiteralPath (Join-Path $Root 'docs\USER_GUIDE.md') `
    -Destination (Join-Path $StageApp 'README.md') -Force

$Forbidden = Get-ChildItem -LiteralPath $StageApp -Recurse -Force | Where-Object {
    $RelativePath = $_.FullName.Substring($StageApp.Length).TrimStart('\')
    $RelativePath -eq 'history.json' -or
    $RelativePath -match '^(models|logs|tmp)(\\|$)'
}
if ($Forbidden) {
    throw "Private runtime data entered the release package: $($Forbidden.FullName -join ', ')"
}

if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
Compress-Archive -Path $StageApp -DestinationPath $Archive -CompressionLevel Optimal
& (Join-Path $PSScriptRoot 'update_release_hashes.ps1')
Write-Host "Built clean release archive: $Archive"
