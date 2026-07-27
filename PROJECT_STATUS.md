# Nassay project status

Last reviewed: 2026-07-27

## Source of truth

- Repository: `https://github.com/Nassay3/Nassay`
- Default and only working branch: `main`
- Start command: `python run.py` on Windows, `python3 run.py` on macOS/Linux
- Application: `http://localhost:5173`
- API health: `http://localhost:5000/api/healthz`

## Current product

- Binance Global Spot and USD-M perpetual Futures selection.
- Japanese, hollow, and Heikin-Ashi candle styles.
- Correct intraday, daily, weekly, and monthly candle spacing.
- Persisted symbol, market, timeframe, candle style, chart range, pane order, pane sizes, and indicator settings.
- Synchronized crosshair across the main chart and lower indicator panes.
- Per-indicator styling and per-timeframe visibility.
- Independent ZScore 48/84 lines and -2/-1/0/1/2 levels.
- Session VWAP group visibility with independent Asia, London, New York, daily, and band styling.
- Draggable and resizable lower panes without overlap.

## Deliberately removed

- Main-chart red/green volume histogram.
- Order Book.
- Recent Trades.
- `BEFORE ITS TOO LATE`.
- Obsolete full-chart update script.

## Data checks already validated

- Binance Global Spot and Futures symbols and live ticker data.
- Futures best bid/ask.
- Daily candles at one-day boundaries.
- Weekly candles at seven-day spacing.
- Monthly candles at UTC month starts.
- Futures second-based intervals return HTTP 400 instead of misleading candles.

## Device synchronization

- `run.py` safely checks `origin/main` before startup.
- It only fast-forwards automatically when the working tree is clean and local `main` has no unpublished commits.
- Dependency installation is refreshed whenever `pnpm-lock.yaml` changes.
- Never edit on two devices concurrently. Publish or commit on one device before switching to the other.
- Local secrets such as `.env` files must remain outside Git.

## Required validation before publishing

```text
pnpm run typecheck
pnpm --filter @workspace/trading-terminal run build
pnpm --filter @workspace/api-server run build
git diff --check
```
