# Deployment to a Windows VPS (demo only)

This happens no earlier than **Stage 7**, after the backtest results have been reviewed.

## 1. VPS selection
- Windows Server 2022 (or Windows 10/11), 2 vCPU, 4 GB RAM, 60 GB SSD is enough for one
  terminal and one bot.
- Choose the region by **measured ping** to the Vantage server shown in MT5 (the bottom-right
  connection indicator). Vantage may also offer a VPS offer for clients; check this before
  paying for a third-party one.
- You can manage it from the iPhone with the Microsoft "Windows App" (RDP client).

## 2. One-time setup (done by you over RDP; the bot never sees credentials)
1. Install the MT5 terminal **from Vantage's official site**.
2. Log in to the **demo** account in the terminal and tick "Save password" (stored by MT5, not us).
3. Tools → Options → Expert Advisors: enable Algo Trading.
4. Install Python 3.12 x64 from python.org and Git for Windows.
5. `git clone` the repo → `python -m venv .venv` → `pip install -e .[mt5]`.
6. Copy `config/default.yaml` to `config/local.yaml` (git-ignored). Set the terminal path
   and the resolved symbol.
7. Run `adamantem doctor`. It checks the terminal connection, that the account is **demo**,
   the symbol spec, server time offset, and that `order_check` works. It sends no orders.

## 3. Running unattended
- Register the bot as a service with **NSSM** (or Task Scheduler "at startup", restart on
  failure). The MT5 terminal is started first by a startup task.
- Windows Update: active hours set, auto-restart outside trading hours; the bot reconciles
  on start.
- Time sync: `w32tm /resync` scheduled; health check alerts when drift > 2 s.
- Logs: rotating JSON files plus the SQLite journal. A daily report is pushed to an optional
  notifier.

## 4. Updating
`git pull` on a tagged release → run the test suite on the VPS → restart the service.
Never deploy an untagged commit.

## 5. Explicitly out of scope
Live (real-money) trading. Moving to live would need a separate, written review of at least
3 months / 100 demo trades compared against the backtest. That decision is yours, and the
code has no switch for it today.
