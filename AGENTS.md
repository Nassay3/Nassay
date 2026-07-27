# Nassay repository guidance

## Start here

- Read `PROJECT_STATUS.md` before making material changes.
- Treat `main` on `https://github.com/Nassay3/Nassay` as the source of truth.
- Preserve user chart settings and migrations in `TradingContext.tsx`.
- Do not restore Order Book, Recent Trades, the main-chart volume histogram, or the removed `BEFORE ITS TOO LATE` indicator unless explicitly requested.

## Workflow

- Before editing, run `git status -sb` and `git pull --ff-only origin main` when the tree is clean.
- Never overwrite or discard uncommitted user changes.
- Keep Windows and macOS support in `run.py`.
- Update `PROJECT_STATUS.md` when behavior, architecture, setup, or validation materially changes.
- Regenerate typed clients after OpenAPI changes with `pnpm --filter @workspace/api-spec run codegen`.

## Validation

- Run `pnpm run typecheck` for all code changes.
- Run the affected production builds for frontend or API changes.
- For candle or indicator changes, validate representative intraday, daily, weekly, and monthly data.
- Keep `git diff --check` clean before publishing.

## Product priorities

- TradingView-like chart interaction and stable pane behavior.
- Correct Binance Global Spot and USD-M perpetual Futures data.
- Correct higher-timeframe candle boundaries and labels.
- Independent, professional indicator styling and per-timeframe visibility.
- Persist all user-visible chart and layout preferences locally.
