/**
 * Binance Data Vision + REST historical kline fetcher.
 * Design goals: maximum speed via full parallelism + in-memory cache.
 *
 *  1. Monthly ZIPs  — bulk; one ZIP covers ~720–744 candles on 1h, all parallel.
 *  2. Daily ZIPs    — cover days not yet in the current month ZIP, all parallel.
 *  3. REST API      — fill the tail gap (today and yesterday not yet published),
 *                     with parallel pagination when the gap spans >1000 candles.
 *  4. In-memory LRU cache  — 90-second TTL per (symbol, interval, days) key.
 */

import { logger } from "./logger";
import type { Candle } from "./vwapIndicators";

const VISION_BASE = "https://data.binance.vision/data/spot";
const BINANCE_API = "https://api.binance.us";

// ── In-memory cache ───────────────────────────────────────────────────────────

interface CacheEntry {
  candles: Candle[];
  fetchedAt: number;
}
const cache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 90_000; // 90 s

function cacheGet(key: string): Candle[] | null {
  const e = cache.get(key);
  if (!e) return null;
  if (Date.now() - e.fetchedAt > CACHE_TTL_MS) { cache.delete(key); return null; }
  return e.candles;
}

function cacheSet(key: string, candles: Candle[]): void {
  // Evict oldest entries when cache grows beyond 100 keys
  if (cache.size >= 100) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].fetchedAt - b[1].fetchedAt)[0];
    if (oldest) cache.delete(oldest[0]);
  }
  cache.set(key, { candles, fetchedAt: Date.now() });
}

// ── Date helpers ──────────────────────────────────────────────────────────────

function ymd(d: Date): string {
  return d.toISOString().split("T")[0];
}

function ym(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

/** List every UTC day in [start, end] as YYYY-MM-DD strings */
function daysBetween(start: Date, end: Date): string[] {
  const days: string[] = [];
  const cur = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
  const endDay = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate()));
  while (cur <= endDay) {
    days.push(ymd(cur));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return days;
}

/** List every YYYY-MM in [start, end] */
function monthsBetween(start: Date, end: Date): string[] {
  const months: string[] = [];
  const cur = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
  const endMonth = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1));
  while (cur <= endMonth) {
    months.push(ym(cur));
    cur.setUTCMonth(cur.getUTCMonth() + 1);
  }
  return months;
}

// ── ZIP fetch + parse ─────────────────────────────────────────────────────────

async function fetchZip(url: string): Promise<Candle[] | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) {
      if (res.status === 404) return null;
      logger.debug({ url, status: res.status }, "Data Vision ZIP not found");
      return null;
    }
    const buf = Buffer.from(await res.arrayBuffer());
    // Use synchronous unzip — fast in Node, no overhead of async wrapper
    const { unzipSync } = await import("node:zlib");
    const csv = unzipSync(buf).toString("utf-8");
    return parseCsv(csv);
  } catch (err) {
    logger.debug({ err, url }, "ZIP fetch failed");
    return null;
  }
}

function parseCsv(csv: string): Candle[] {
  const lines = csv.trim().split("\n");
  const out: Candle[] = [];
  for (const line of lines) {
    if (!line || line.startsWith("open")) continue; // skip header if present
    const c = line.split(",");
    if (c.length < 9) continue;
    out.push({
      openTime:            parseInt(c[0], 10),
      open:                c[1],
      high:                c[2],
      low:                 c[3],
      close:               c[4],
      volume:              c[5],
      closeTime:           parseInt(c[6], 10),
      quoteVolume:         c[7],
      trades:              parseInt(c[8], 10),
      takerBuyBaseVolume:  c[9]  ?? "0",
      takerBuyQuoteVolume: c[10] ?? "0",
    });
  }
  return out;
}

// ── REST fallback (parallel pagination) ───────────────────────────────────────

async function restPage(symbol: string, interval: string, startTime: number, endTime: number): Promise<Candle[]> {
  const url = new URL(`${BINANCE_API}/api/v3/klines`);
  url.searchParams.set("symbol",    symbol);
  url.searchParams.set("interval",  interval);
  url.searchParams.set("startTime", String(startTime));
  url.searchParams.set("endTime",   String(endTime));
  url.searchParams.set("limit",     "1000");
  const res = await fetch(url.toString());
  if (!res.ok) return [];
  const raw = (await res.json()) as Array<[number, string, string, string, string, string, number, string, number, string, string, string]>;
  return raw.map((c) => ({
    openTime:            c[0],
    open:                c[1],
    high:                c[2],
    low:                 c[3],
    close:               c[4],
    volume:              c[5],
    closeTime:           c[6],
    quoteVolume:         c[7],
    trades:              c[8],
    takerBuyBaseVolume:  c[9],
    takerBuyQuoteVolume: c[10],
  }));
}

function intervalToMs(interval: string): number {
  const unit  = interval.slice(-1);
  const value = parseInt(interval.slice(0, -1), 10) || 1;
  switch (unit) {
    case "m": return value * 60_000;
    case "h": return value * 3_600_000;
    case "d": return value * 86_400_000;
    case "w": return value * 7 * 86_400_000;
    default:  return 60_000;
  }
}

/** Fetch the entire REST gap in parallel pages */
async function fetchRestGap(symbol: string, interval: string, gapStart: number, gapEnd: number): Promise<Candle[]> {
  const barMs   = intervalToMs(interval);
  const gapBars = Math.ceil((gapEnd - gapStart) / barMs);
  const pages   = Math.max(1, Math.ceil(gapBars / 1000));

  // Build page boundaries upfront and fire them all in parallel
  const tasks: Promise<Candle[]>[] = [];
  for (let p = 0; p < pages; p++) {
    const pStart = gapStart + p * 1000 * barMs;
    const pEnd   = Math.min(gapStart + (p + 1) * 1000 * barMs - 1, gapEnd);
    tasks.push(restPage(symbol, interval, pStart, pEnd));
  }

  const results = await Promise.all(tasks);
  return results.flat();
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function fetchHistoricalKlines(
  symbol: string,
  interval: string,
  days: number,
): Promise<Candle[]> {
  const cacheKey = `${symbol}:${interval}:${days}`;
  const cached   = cacheGet(cacheKey);
  if (cached) {
    logger.debug({ symbol, interval, days, count: cached.length }, "Serving from cache");
    return cached;
  }

  const now   = Date.now();
  const end   = new Date(now);
  const start = new Date(now - days * 86_400_000);

  // ── 1. Monthly ZIPs — all in parallel ─────────────────────────────────────
  const months       = monthsBetween(start, end);
  const monthPromises = months.map((month) =>
    fetchZip(`${VISION_BASE}/monthly/klines/${symbol}/${interval}/${symbol}-${interval}-${month}.zip`),
  );
  const monthResults = await Promise.all(monthPromises);

  const pool: Candle[] = [];
  const coveredDays   = new Set<string>();

  for (const candles of monthResults) {
    if (!candles?.length) continue;
    for (const c of candles) {
      coveredDays.add(ymd(new Date(c.openTime)));
    }
    pool.push(...candles);
  }

  // ── 2. Daily ZIPs — parallel, only days not already covered ───────────────
  const allDays   = daysBetween(start, end);
  const missDays  = allDays.filter((d) => !coveredDays.has(d));

  if (missDays.length > 0) {
    const dailyPromises = missDays.map((day) =>
      fetchZip(`${VISION_BASE}/daily/klines/${symbol}/${interval}/${symbol}-${interval}-${day}.zip`),
    );
    const dailyResults = await Promise.all(dailyPromises);
    for (const candles of dailyResults) {
      if (candles?.length) pool.push(...candles);
    }
  }

  // ── 3. REST tail — only what's not yet in Data Vision ─────────────────────
  let latestClose = 0;
  for (const c of pool) if (c.closeTime > latestClose) latestClose = c.closeTime;

  const gapStart = latestClose > 0 ? latestClose + 1 : start.getTime();
  if (gapStart < now) {
    try {
      const tail = await fetchRestGap(symbol, interval, gapStart, now);
      pool.push(...tail);
    } catch (err) {
      logger.error({ err, symbol }, "REST gap fill failed");
    }
  }

  // ── 4. Sort + deduplicate + filter to requested window ────────────────────
  pool.sort((a, b) => a.openTime - b.openTime);
  const seen   = new Set<number>();
  const unique: Candle[] = [];
  const windowStart = start.getTime();
  for (const c of pool) {
    if (c.openTime < windowStart) continue;
    if (seen.has(c.openTime)) continue;
    seen.add(c.openTime);
    unique.push(c);
  }

  logger.info({ symbol, interval, days, count: unique.length }, "Historical data fetched");
  cacheSet(cacheKey, unique);
  return unique;
}
