import { logger } from "./logger";
import type { Candle } from "./vwapIndicators";

const VISION_BASE = "https://data.binance.vision/data/spot";
const BINANCE_API = "https://api.binance.us";

function formatDate(date: Date): string {
  return date.toISOString().split("T")[0];
}

function formatMonth(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

async function fetchCsvZip(url: string): Promise<string | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      if (response.status === 404) return null;
      throw new Error(`Data Vision error ${response.status}: ${await response.text()}`);
    }
    const buffer = await response.arrayBuffer();
    const { unzipSync } = await import("node:zlib");
    const unzipped = unzipSync(Buffer.from(buffer));
    return unzipped.toString("utf-8");
  } catch (err) {
    // 404s or broken zips are expected for dates that have not been published yet
    logger.debug({ err, url }, "Data Vision CSV not available for date");
    return null;
  }
}

function parseCsvKlines(csv: string): Candle[] {
  const lines = csv.trim().split("\n");
  return lines.map((line) => {
    const cols = line.split(",");
    return {
      openTime: parseInt(cols[0], 10),
      open: cols[1],
      high: cols[2],
      low: cols[3],
      close: cols[4],
      volume: cols[5],
      closeTime: parseInt(cols[6], 10),
      quoteVolume: cols[7],
      trades: parseInt(cols[8], 10),
      takerBuyBaseVolume: cols[9],
      takerBuyQuoteVolume: cols[10],
    };
  });
}

async function fetchRestKlines(symbol: string, interval: string, startTime: number, endTime: number): Promise<Candle[]> {
  const url = new URL(`${BINANCE_API}/api/v3/klines`);
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("interval", interval);
  url.searchParams.set("startTime", String(startTime));
  url.searchParams.set("endTime", String(endTime));
  url.searchParams.set("limit", "1000");
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Binance REST error ${response.status}: ${await response.text()}`);
  }
  const raw = (await response.json()) as Array<[number, string, string, string, string, string, number, string, number, string, string, string]>;
  return raw.map((c) => ({
    openTime: c[0],
    closeTime: c[6],
    open: c[1],
    high: c[2],
    low: c[3],
    close: c[4],
    volume: c[5],
    quoteVolume: c[7],
    trades: c[8],
    takerBuyBaseVolume: c[9],
    takerBuyQuoteVolume: c[10],
  }));
}

export async function fetchHistoricalKlines(symbol: string, interval: string, days: number): Promise<Candle[]> {
  const candles: Candle[] = [];
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
  const current = new Date(start);

  let latestDataTime: number | null = null;

  while (current <= end) {
    const dayUrl = `${VISION_BASE}/daily/klines/${symbol}/${interval}/${symbol}-${interval}-${formatDate(current)}.zip`;
    const csv = await fetchCsvZip(dayUrl);
    if (csv) {
      const dayCandles = parseCsvKlines(csv);
      candles.push(...dayCandles);
      if (dayCandles.length > 0) {
        latestDataTime = Math.max(latestDataTime ?? 0, dayCandles[dayCandles.length - 1].closeTime);
      }
    }
    current.setUTCDate(current.getUTCDate() + 1);
  }

  // If we got no daily data, try monthly as fallback for older ranges
  if (candles.length === 0 && days > 30) {
    const monthUrl = `${VISION_BASE}/monthly/klines/${symbol}/${interval}/${symbol}-${interval}-${formatMonth(start)}.zip`;
    const csv = await fetchCsvZip(monthUrl);
    if (csv) {
      const monthCandles = parseCsvKlines(csv);
      candles.push(...monthCandles);
      if (monthCandles.length > 0) {
        latestDataTime = Math.max(latestDataTime ?? 0, monthCandles[monthCandles.length - 1].closeTime);
      }
    }
  }

  // Fill any gap with REST API for the requested range
  if (latestDataTime) {
    if (latestDataTime < end.getTime()) {
      try {
        const restCandles = await fetchRestKlines(symbol, interval, latestDataTime + 1, end.getTime());
        candles.push(...restCandles);
      } catch (err) {
        logger.error({ err, symbol }, "Failed to fill gap with REST API");
      }
    }
  } else {
    // No Data Vision data at all for the requested range, use REST API for the whole range
    try {
      const restCandles = await fetchRestKlines(symbol, interval, start.getTime(), end.getTime());
      candles.push(...restCandles);
    } catch (err) {
      logger.error({ err, symbol }, "Failed to fetch historical data from REST API");
    }
  }

  // Sort by time and remove duplicates
  candles.sort((a, b) => a.openTime - b.openTime);
  const seen = new Set<number>();
  const unique: Candle[] = [];
  for (const c of candles) {
    if (!seen.has(c.openTime)) {
      seen.add(c.openTime);
      unique.push(c);
    }
  }
  return unique;
}
