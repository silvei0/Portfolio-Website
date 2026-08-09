$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $scriptDirectory "launch-project-manager.cmd"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "The project-manager launcher was not found: $launcher"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Portfolio Project Manager.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $scriptDirectory
$shortcut.Description = "Create and publish project posts for Fiza's Project Portfolio"
$portfolioIcon = Join-Path (Split-Path -Parent $scriptDirectory) "assets\site-icon.ico"
if (Test-Path -LiteralPath $portfolioIcon) {
    $shortcut.IconLocation = $portfolioIcon
} else {
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,71"
}
$shortcut.Save()

Write-Host "Desktop shortcut created:" -ForegroundColor Green
Write-Host $shortcutPath
