# Nassay trading terminal

Nassay is a professional Binance Global charting terminal for Spot and USD-M perpetual Futures.

## Run and operate

- `python run.py` on Windows or `python3 run.py` on macOS/Linux: safely sync a clean `main`, prepare the private Node/pnpm runtime, install current dependencies, and start the complete app.
- `pnpm dev`: run the API on port 5000 and terminal on port 5173.
- `pnpm run typecheck`: full workspace typecheck.
- `pnpm run build`: typecheck and build all packages.
- `pnpm --filter @workspace/api-spec run codegen`: regenerate hooks and Zod schemas after OpenAPI changes.
- Optional `OPENROUTER_API_KEY`: enables the AI chat panel; the market terminal works without it.
- Optional `DATABASE_URL`: enables database-backed features.

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- React, Vite, and Lightweight Charts
- Express 5 API
- Zod/OpenAPI generated clients
- Binance Global REST, archive, and WebSocket market data

## Repository map

- `artifacts/trading-terminal`: React chart terminal.
- `artifacts/api-server`: Express API, Binance data, and indicator calculations.
- `lib/api-spec`: source OpenAPI contract.
- `lib/api-client-react` and `lib/api-zod`: generated API clients and schemas.
- `run.py`: cross-platform launcher and safe Git synchronization.
- `AGENTS.md`: durable Codex repository instructions.
- `PROJECT_STATUS.md`: current product state, decisions, and validation record.

## Architecture decisions

- `main` on `Nassay3/Nassay` is the only code source of truth.
- `run.py` only auto-updates with a clean, non-diverged `main`.
- Candle timestamps and visible ranges remain native to their selected timeframe.
- User chart, layout, candle, market, and indicator preferences persist locally.
- Lower panes have synchronized crosshairs and independent scale interaction.

## Product priorities

- TradingView-like chart interaction.
- Accurate higher-timeframe candles.
- Professional independent indicator controls.
- Stable draggable and resizable lower panes.
- Reliable Binance Global Spot and USD-M Futures switching.

## Gotchas

- Do not edit concurrently on two devices. Publish one device before switching.
- Do not put `.env`, `node_modules`, or `.runtime` in Git.
- Do not restore removed Order Book, Recent Trades, main-chart volume, or `BEFORE ITS TOO LATE` without an explicit request.
- Read `PROJECT_STATUS.md` before material changes.
