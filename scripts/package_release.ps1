[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root 'release'
$AppDir = Join-Path $ReleaseDir 'VoxCortex'
$StageRoot = Join-Path $Root '.build\release-package'
$StageApp = Join-Path $StageRoot 'VoxCortex'
$Version = (Get-Content -LiteralPath (Join-Path $Root 'firmware\version.json') -Raw |
    ConvertFrom-Json).version
$Archive = Join-Path $ReleaseDir "VoxCortex-$Version-windows.zip"
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$ExcludedRuntimeItems = @('models', 'history.json', 'logs', 'tmp', 'config.yaml')

$RootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
$StageFull = [IO.Path]::GetFullPath($StageRoot)
if (-not $StageFull.StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe release staging path: $StageFull"
}
if (-not (Test-Path -LiteralPath (Join-Path $AppDir 'VoxCortex.exe'))) {
    throw 'Windows application not found. Run .\scripts\build_server_exe.ps1 first.'
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Virtual environment not found. Run .\scripts\setup_windows.ps1 first.'
}

if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StageApp -Force | Out-Null

Get-ChildItem -LiteralPath $AppDir -Force |
    Where-Object { $_.Name -notin $ExcludedRuntimeItems } |
    Copy-Item -Destination $StageApp -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Root 'pc_server\config.example.yaml') `
    -Destination (Join-Path $StageApp 'config.example.yaml') -Force
Copy-Item -LiteralPath (Join-Path $Root 'docs\USER_GUIDE.md') `
    -Destination (Join-Path $StageApp 'README.md') -Force

$Forbidden = Get-ChildItem -LiteralPath $StageApp -Recurse -Force | Where-Object {
    $RelativePath = $_.FullName.Substring($StageApp.Length).TrimStart('\')
    $RelativePath -eq 'history.json' -or
    $RelativePath -eq 'config.yaml' -or
    $RelativePath -match '^(models|logs|tmp)(\\|$)'
}
if ($Forbidden) {
    throw "Private runtime data entered the release package: $($Forbidden.FullName -join ', ')"
}

if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
Compress-Archive -Path $StageApp -DestinationPath $Archive -CompressionLevel Optimal
& $Python (Join-Path $Root 'tools\verify_release_archive.py') $Archive
if ($LASTEXITCODE -ne 0) {
    throw 'Release archive validation failed.'
}
& (Join-Path $PSScriptRoot 'update_release_hashes.ps1')
Write-Host "Built clean release archive: $Archive"
