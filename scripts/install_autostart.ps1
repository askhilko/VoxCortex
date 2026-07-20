[CmdletBinding(SupportsShouldProcess)]
param()
$Root = Split-Path -Parent $PSScriptRoot
$Startup = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'VoxCortex.lnk'
$Exe = Join-Path $Root 'release\VoxCortex\VoxCortex.exe'
if ($PSCmdlet.ShouldProcess($ShortcutPath, 'Create startup shortcut')) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    if (Test-Path -LiteralPath $Exe) {
        $Shortcut.TargetPath = $Exe
        $Shortcut.WorkingDirectory = Split-Path -Parent $Exe
        $Shortcut.IconLocation = "$Exe,0"
    } else {
        $Shortcut.TargetPath = 'powershell.exe'
        $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\start_server.ps1`""
        $Shortcut.WorkingDirectory = $Root
    }
    $Shortcut.Save()
    Write-Host "Created $ShortcutPath"
}
