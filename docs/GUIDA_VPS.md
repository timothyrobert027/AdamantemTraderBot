# Guida: il bot ADAMANTEM sul conto demo, solo dall'iPhone

Il bot gira su un **VPS Windows** (un computer nel cloud, acceso 24 ore su 24). Tu lo controlli
dall'iPhone con l'app **Windows App** di Microsoft. Le password le scrivi solo tu, nei campi
giusti: non vanno mai in chat, nei file o su GitHub.

## 1. Conto demo Vantage (app Vantage)
- Apri un conto **demo MT5**, tipo **Standard**, possibilmente **hedging**.
- Annota numero di conto e nome del server. La password tienila per te.

## 2. VPS Windows (Safari)
- Prima guarda nel portale Vantage se offrono un VPS per i clienti.
- Altrimenti noleggia un VPS **Windows Server 2019/2022**, 2 vCPU, 4 GB RAM, datacenter a
  Londra o New York, **licenza Windows inclusa**. Il provider ti dà IP, utente e password.

## 3. Collegarti (app "Windows App")
- **+** → **Aggiungi PC** → IP del VPS → utente e password.
- Per uscire **chiudi l'app senza disconnettere l'utente** (non fare "Esci" da Windows): così
  MT5 e il bot restano accesi.

## 4. MT5 sul VPS
- Nel browser del VPS scarica **MT5 dal sito ufficiale Vantage** e installalo.
- Accedi al **conto demo**, spunta **Salva password**, premi **Algo Trading** (verde).
- In basso a destra deve risultare connesso.

## 5. Installare il bot (un solo comando)
- Sul VPS apri **PowerShell come amministratore** (tasto destro su Start → Terminale (Admin)).
- Incolla:
  ```
  Set-ExecutionPolicy Bypass -Scope Process -Force; iwr https://raw.githubusercontent.com/timothyrobert027/AdamantemTraderBot/claude/adamantem-trader-architecture-wgs85o/scripts/setup_vps.ps1 -OutFile $env:TEMP\setup.ps1; & $env:TEMP\setup.ps1
  ```
  Se il repository è privato quel link non funziona: in quel caso apri il file
  `scripts/setup_vps.ps1` dall'app GitHub, copia il contenuto e incollalo in PowerShell.
- Quando Git lo chiede, accedi a GitHub nella finestra che si apre (è il login di GitHub, non
  quello del broker).

## 6. Controllo in sola lettura
- In PowerShell: `C:\adamantem\scripts\doctor.ps1`
- Controlla che il conto sia demo, legge simbolo, lotto minimo, spread reale e orario del
  server, ed esporta lo storico Vantage su GitHub. **Non invia ordini.**
- Scrivimi "doctor fatto": ricalcolo il backtest con i dati e gli spread veri di Vantage.

## 7. Avvio del bot in demo
- Esci e rientra nel VPS (oppure riavvialo): l'attività **"ADAMANTEM demo"** parte da sola.
- `C:\adamantem\state\heartbeat.txt` mostra l'ultimo ciclo; `state\journal.jsonl` ogni decisione.
- In MT5 vedrai gli ordini limit con stop e target, commento "ADM".
