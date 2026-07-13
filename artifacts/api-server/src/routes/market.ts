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
import { fetchHistoricalKlines } from "../lib/binanceVision";
import { calculateVwapIndicators } from "../lib/vwapIndicators";

const router: IRouter = Router();
const BINANCE_API = "https://api.binance.us";

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
