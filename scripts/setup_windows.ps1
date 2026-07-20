[CmdletBinding()]
param([switch]$SkipModel)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = $null
$Candidates = @(
    [pscustomobject]@{ Exe = 'py'; Args = @('-3.12') },
    [pscustomobject]@{ Exe = 'py'; Args = @('-3.11') },
    [pscustomobject]@{ Exe = 'py'; Args = @('-3.14') },
    [pscustomobject]@{ Exe = 'python'; Args = @() }
)
foreach ($Candidate in $Candidates) {
    try {
        $Version = & $Candidate.Exe @($Candidate.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($Version -in @('3.11','3.12','3.14')) { $Python = $Candidate; break }
    } catch {}
}
if (-not $Python) { throw 'Python 3.11, 3.12, or 3.14 is required. Install it from python.org.' }

& $Python.Exe @($Python.Args) -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".\pc_server[speech,firmware]"

$ConfigPath = & .\.venv\Scripts\python.exe -c "from voxcortex.config import prepare_user_config; print(prepare_user_config())"
Write-Host "User configuration: $ConfigPath"

if (-not $SkipModel) {
    $Download = Read-Host 'Download/load the configured faster-whisper model now? [y/N]'
    if ($Download -match '^[yY]') {
        & .\.venv\Scripts\python.exe -c "from voxcortex.config import load_settings, prepare_user_config; from voxcortex.transcriber import WhisperTranscriber; settings=load_settings(prepare_user_config()); WhisperTranscriber(settings.speech).load(); print(f'Model ready: {settings.speech.models_dir}')"
    }
}

$Address = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'
} | Select-Object -ExpandProperty IPAddress
Write-Host "PC IPv4 address(es): $($Address -join ', ')"
$Port = 8765
$InUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($InUse) { Write-Warning "Port $Port is already in use." } else { Write-Host "Port $Port is available." }
Write-Host "If the M5 cannot connect, allow TCP port $Port for Private networks in Windows Firewall."
Write-Host "Edit $ConfigPath, then run .\scripts\start_server.ps1"
