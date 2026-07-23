import { Router, type IRouter } from "express";
import { logger } from "../lib/logger";
import {
  ListSymbolsQueryParams,
  ListSymbolsResponse,
  GetHistoryQueryParams,
  GetHistoryResponse,
  GetVwapQueryParams,
  GetVwapResponse,
  Get24hrTickerQueryParams,
  Get24hrTickerResponse,
} from "@workspace/api-zod";
import { fetchChartWindow, fetchHistoricalKlines, fetchHistoricalWindow, intervalToMs } from "../lib/binanceVision";
import {
  calculateVwapIndicators,
  getRequiredDashboardIntervals,
  getRequiredVwmaMtfDefinitions,
  trimVwapIndicators,
  type Candle,
  type MtfCandleSources,
} from "../lib/vwapIndicators";

const router: IRouter = Router();
const BINANCE_API = "https://data-api.binance.vision";

function aggregateCandles(candles: Candle[], targetIntervalMs: number): Candle[] {
  const buckets = new Map<number, Candle>();
  for (const candle of candles) {
    const bucketOpen = Math.floor(candle.openTime / targetIntervalMs) * targetIntervalMs;
    const existing = buckets.get(bucketOpen);
    if (!existing) {
      buckets.set(bucketOpen, {
        ...candle,
        openTime: bucketOpen,
        closeTime: bucketOpen + targetIntervalMs - 1,
      });
      continue;
    }
    existing.high = String(Math.max(Number(existing.high), Number(candle.high)));
    existing.low = String(Math.min(Number(existing.low), Number(candle.low)));
    existing.close = candle.close;
    existing.volume = String(Number(existing.volume) + Number(candle.volume));
    existing.quoteVolume = String(Number(existing.quoteVolume) + Number(candle.quoteVolume));
    existing.trades += candle.trades;
    existing.takerBuyBaseVolume = String(Number(existing.takerBuyBaseVolume) + Number(candle.takerBuyBaseVolume));
    existing.takerBuyQuoteVolume = String(Number(existing.takerBuyQuoteVolume) + Number(candle.takerBuyQuoteVolume));
  }
  const aggregated = [...buckets.values()].sort((a, b) => a.openTime - b.openTime);
  if (aggregated.length && candles[0]?.openTime !== aggregated[0].openTime) aggregated.shift();
  return aggregated;
}

async function fetchVwmaMtfSources(
  symbol: string,
  interval: string,
  endTime: number,
): Promise<MtfCandleSources> {
  const definitions = getRequiredVwmaMtfDefinitions(interval);
  const entries = await Promise.all(definitions.map(async (definition) => {
    const maximumPeriod = Math.max(...definition.periods);
    if (definition.interval === "45m") {
      const base = await fetchHistoricalWindow(symbol, "15m", maximumPeriod * 3 + 6, endTime);
      return [definition.interval, aggregateCandles(base, 45 * 60_000)] as const;
    }
    const series = await fetchHistoricalWindow(symbol, definition.interval, maximumPeriod + 4, endTime);
    return [definition.interval, series] as const;
  }));
  return Object.fromEntries(entries);
}

const dashboardSourceCache = new Map<string, { endTime: number; promise: Promise<MtfCandleSources> }>();

async function fetchDashboardSources(symbol: string, endTime: number): Promise<MtfCandleSources> {
  const cached = dashboardSourceCache.get(symbol);
  // A chart refresh should reuse the same dashboard snapshot; the HTTP response itself
  // is allowed to stay stale for 60 seconds and the ten fixed-frame reads are expensive.
  if (cached && Math.abs(endTime - cached.endTime) < 60_000) return cached.promise;
  const promise = Promise.all(getRequiredDashboardIntervals().map(async (sourceInterval) => {
    const series = await fetchChartWindow(symbol, sourceInterval, 1_900, endTime);
    return [sourceInterval, series] as const;
  })).then((entries) => Object.fromEntries(entries));
  dashboardSourceCache.set(symbol, { endTime, promise });
  if (dashboardSourceCache.size > 8) dashboardSourceCache.delete(dashboardSourceCache.keys().next().value!);
  try {
    return await promise;
  } catch (error) {
    if (dashboardSourceCache.get(symbol)?.promise === promise) dashboardSourceCache.delete(symbol);
    throw error;
  }
}

router.get("/market/chart", async (req, res): Promise<void> => {
  const symbol = String(req.query.symbol ?? "BTCUSDT").toUpperCase();
  const interval = String(req.query.interval ?? "1h");
  const limit = Math.max(2, Math.min(Number(req.query.limit) || 4_000, 8_000));
  const requestedEnd = Number(req.query.endTime) || Date.now();
  const barMs = intervalToMs(interval);
  const weekWarmup = Math.ceil((8 * 86_400_000) / barMs);
  const warmupBars = Math.max(1_000, weekWarmup);
  const startedAt = performance.now();

  try {
    const [source, mtfSources, dashboardSources] = await Promise.all([
      fetchChartWindow(symbol, interval, limit + warmupBars, requestedEnd),
      fetchVwmaMtfSources(symbol, interval, requestedEnd),
      fetchDashboardSources(symbol, requestedEnd),
    ]);
    if (!source.length) {
      res.status(502).json({ error: "No market data returned" });
      return;
    }

    const requested = source.slice(-limit);
    const calculationStartedAt = performance.now();
    const calculated = calculateVwapIndicators(source, symbol, interval, { ...mtfSources, ...dashboardSources });
    const indicators = trimVwapIndicators(calculated, requested[0].openTime);
    const finishedAt = performance.now();

    res.setHeader("Cache-Control", "public, max-age=15, stale-while-revalidate=60");
    res.setHeader(
      "Server-Timing",
      `fetch;dur=${(calculationStartedAt - startedAt).toFixed(1)}, calculate;dur=${(finishedAt - calculationStartedAt).toFixed(1)}`,
    );
    res.json({
      symbol,
      interval,
      candles: requested,
      indicators,
      hasMore: source.length >= limit + Math.min(warmupBars, 1_000),
      nextEndTime: requested[0].openTime - 1,
      timing: {
        fetchMs: Math.round(calculationStartedAt - startedAt),
        calculateMs: Math.round(finishedAt - calculationStartedAt),
      },
    });
  } catch (err) {
    logger.error({ err, symbol, interval }, "Failed to build chart page");
    res.status(502).json({ error: err instanceof Error ? err.message : String(err) });
  }
});

async function binanceFetch<T>(path: string, params: Record<string, string | number | undefined>): Promise<T> {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const url = `${BINANCE_API}${path}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Binance API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

router.get("/market/symbols", async (req, res): Promise<void> => {
  const parsed = ListSymbolsQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const quote = parsed.data.quote?.toUpperCase() ?? "USDT";
  try {
    const info = await binanceFetch<{
      symbols: Array<{
        symbol: string;
        baseAsset: string;
        quoteAsset: string;
        status: string;
        filters: Array<{ filterType: string; minPrice?: string; maxPrice?: string; tickSize?: string; minQty?: string; stepSize?: string }>;
      }>;
    }>("/api/v3/exchangeInfo", {});

    const symbols = info.symbols
      .filter((s) => s.quoteAsset === quote && s.status === "TRADING")
      .map((s) => {
        const priceFilter = s.filters.find((f) => f.filterType === "PRICE_FILTER");
        const lotSize = s.filters.find((f) => f.filterType === "LOT_SIZE");
        return {
          symbol: s.symbol,
          baseAsset: s.baseAsset,
          quoteAsset: s.quoteAsset,
          status: s.status,
          minPrice: priceFilter?.minPrice ?? "0",
          maxPrice: priceFilter?.maxPrice ?? "0",
          tickSize: priceFilter?.tickSize ?? "0",
          minQty: lotSize?.minQty ?? "0",
          stepSize: lotSize?.stepSize ?? "0",
        };
      });

    res.json(ListSymbolsResponse.parse({ symbols, count: symbols.length }));
  } catch (err) {
    logger.error({ err }, "Failed to fetch symbols");
    res.status(502).json({ error: err instanceof Error ? err.message : String(err) });
  }
});

router.get("/market/history", async (req, res): Promise<void> => {
  const parsed = GetHistoryQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  try {
    const candles = await fetchHistoricalKlines(parsed.data.symbol, parsed.data.interval, parsed.data.days);
    res.json(GetHistoryResponse.parse({ symbol: parsed.data.symbol, interval: parsed.data.interval, candles }));
  } catch (err) {
    logger.error({ err, symbol: parsed.data.symbol }, "Failed to fetch historical data");
    res.status(502).json({ error: err instanceof Error ? err.message : String(err) });
  }
});

router.get("/market/vwap", async (req, res): Promise<void> => {
  const parsed = GetVwapQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  try {
    const candles = await fetchHistoricalKlines(parsed.data.symbol, parsed.data.interval, parsed.data.days);
    const indicators = calculateVwapIndicators(candles, parsed.data.symbol, parsed.data.interval);
    res.json(GetVwapResponse.parse(indicators));
  } catch (err) {
    logger.error({ err, symbol: parsed.data.symbol }, "Failed to calculate VWAP indicators");
    res.status(502).json({ error: err instanceof Error ? err.message : String(err) });
  }
});

router.get("/market/ticker/24hr", async (req, res): Promise<void> => {
  const parsed = Get24hrTickerQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  try {
    const raw = await binanceFetch<
      Array<{
        symbol: string;
        priceChange: string;
        priceChangePercent: string;
        weightedAvgPrice: string;
        prevClosePrice: string;
        lastPrice: string;
        lastQty: string;
        bidPrice: string;
        bidQty: string;
        askPrice: string;
        askQty: string;
        openPrice: string;
        highPrice: string;
        lowPrice: string;
        volume: string;
        quoteVolume: string;
        openTime: number;
        closeTime: number;
        firstId: number;
        lastId: number;
        count: number;
      }>
    >("/api/v3/ticker/24hr", parsed.data.symbol ? { symbol: parsed.data.symbol } : {});
    const tickers = Array.isArray(raw) ? raw : [raw];
    res.json(Get24hrTickerResponse.parse({ tickers, count: tickers.length }));
  } catch (err) {
    logger.error({ err }, "Failed to fetch 24hr ticker");
    res.status(502).json({ error: err instanceof Error ? err.message : String(err) });
  }
});

export default router;
