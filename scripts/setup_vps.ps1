# ADAMANTEM - one-time setup on the Windows VPS (run in PowerShell as Administrator).
# Installs Python 3.12 and Git if missing, clones the repository, installs the bot,
# finds the MT5 terminal and registers a task that starts the demo bot at logon.
# It never asks for, reads or stores the broker password.

$ErrorActionPreference = "Stop"
$Repo   = "https://github.com/timothyrobert027/AdamantemTraderBot.git"
$Branch = "claude/adamantem-trader-architecture-wgs85o"
$Dir    = "C:\adamantem"

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if (-not (Have "python")) {
    Write-Host "Installing Python 3.12..."
    $py = "$env:TEMP\python-3.12.10-amd64.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $py
    Start-Process $py -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
}
if (-not (Have "git")) {
    Write-Host "Installing Git for Windows..."
    $git = "$env:TEMP\Git-2.47.1-64-bit.exe"
    Invoke-WebRequest "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe" -OutFile $git
    Start-Process $git -ArgumentList "/VERYSILENT /NORESTART" -Wait
}
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Test-Path $Dir)) {
    Write-Host "Cloning the repository (a GitHub sign-in window may open)..."
    git clone --branch $Branch $Repo $Dir
} else {
    git -C $Dir pull
}

Set-Location $Dir
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[mt5]"

$terminal = Get-ChildItem "C:\Program Files", "C:\Program Files (x86)" -Recurse -Filter terminal64.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "Vantage|MetaTrader" } | Select-Object -First 1
if ($terminal) {
    "broker:`n  terminal_path: `"$($terminal.FullName -replace '\\','\\')`"`n" | Set-Content "$Dir\config\local.yaml"
    Write-Host "MT5 terminal found: $($terminal.FullName)"
} else {
    Write-Host "MT5 terminal not found: install MT5 from Vantage, then run this script again."
}

$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$Dir\scripts\run_demo.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "ADAMANTEM demo" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Setup complete. Next: run scripts\doctor.ps1 (read-only check)."
