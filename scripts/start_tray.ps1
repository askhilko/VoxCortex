[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$EntryPoint = Join-Path $Root 'pc_server\tray_entry.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Virtual environment not found. Run .\scripts\setup_windows.ps1 first.'
}

Set-Location $Root
& $Python $EntryPoint
exit $LASTEXITCODE
