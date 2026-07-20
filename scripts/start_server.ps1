$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\pc_server"
& "$Root\.venv\Scripts\m5-dictation-server.exe" --config config.yaml

