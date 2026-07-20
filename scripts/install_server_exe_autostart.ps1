[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root 'release\M5AIDictationServer\M5AIDictationServer.exe'
$AppDir = Split-Path -Parent $Exe
$Startup = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'M5 AI Dictation Server.lnk'

if (-not (Test-Path -LiteralPath $Exe)) {
    throw 'Server EXE not found. Run .\scripts\build_server_exe.ps1 first.'
}

if ($PSCmdlet.ShouldProcess($ShortcutPath, 'Create startup shortcut for tray server')) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Exe
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.IconLocation = "$Exe,0"
    $Shortcut.Save()
    Write-Host "Created $ShortcutPath"
}
