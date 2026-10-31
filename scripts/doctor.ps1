# Read-only check of the MT5 demo connection; exports Vantage history and spreads to exports\.
# Sends no orders. Afterwards it commits and pushes the export so the backtest can use it.
Set-Location "C:\adamantem"
.\.venv\Scripts\python -m adamantem.app.cli doctor
if ($LASTEXITCODE -eq 0) {
    git add exports
    git commit -m "Vantage MT5 export from doctor (read-only)"
    git push
}
