# Starts the demo bot and restarts it if it stops. Started at logon by the scheduled task.
# The MT5 terminal must be open and logged in to the DEMO account in the same Windows session.
Set-Location "C:\adamantem"
New-Item -ItemType Directory -Force -Path state | Out-Null
while ($true) {
    .\.venv\Scripts\python -m adamantem.app.cli demo *>> state\bot.log
    Start-Sleep -Seconds 30
}
