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
import { unzipSync as unzipZip } from "fflate";

export type BinanceMarket = "spot" | "futures";

const VISION_BASES: Record<BinanceMarket, string> = {
  spot: "https://data.binance.vision/data/spot",
  futures: "https://data.binance.vision/data/futures/um",
};

// These are Binance Global production market-data endpoints. Binance US is
// intentionally not used anywhere in the terminal.
const BINANCE_API_BASES: Record<BinanceMarket, string[]> = {
  spot: [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
  ],
  futures: [
    "https://fapi.binance.com",
  ],
};

// ── In-memory cache ───────────────────────────────────────────────────────────

interface CacheEntry {
  candles: Candle[];
  fetchedAt: number;
}
const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<Candle[]>>();
const CACHE_TTL_MS = 5 * 60_000;

interface OneSecondDayEntry {
  candles: Candle[];
  complete: boolean;
  checkedVision: boolean;
  updatedAt: number;
}
const oneSecondDays = new Map<string, OneSecondDayEntry>();

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
    const res = await fetch(url, { signal: AbortSignal.timeout(20_000) });
    if (!res.ok) {
      if (res.status === 404) return null;
      logger.debug({ url, status: res.status }, "Data Vision ZIP not found");
      return null;
    }
    const archive = unzipZip(new Uint8Array(await res.arrayBuffer()));
    const csvFile = Object.entries(archive).find(([name]) => name.endsWith(".csv"));
    if (!csvFile) return null;
    const csv = new TextDecoder().decode(csvFile[1]);
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
    const openTimeRaw = Number(c[0]);
    const closeTimeRaw = Number(c[6]);
    const openTime = openTimeRaw > 10_000_000_000_000 ? Math.floor(openTimeRaw / 1_000) : openTimeRaw;
    const closeTime = closeTimeRaw > 10_000_000_000_000 ? Math.floor(closeTimeRaw / 1_000) : closeTimeRaw;
    out.push({
      openTime,
      open:                c[1],
      high:                c[2],
      low:                 c[3],
      close:               c[4],
      volume:              c[5],
      closeTime,
      quoteVolume:         c[7],
      trades:              parseInt(c[8], 10),
      takerBuyBaseVolume:  c[9]  ?? "0",
      takerBuyQuoteVolume: c[10] ?? "0",
    });
  }
  return out;
}

// ── REST fallback (parallel pagination) ───────────────────────────────────────

async function restPage(
  symbol: string,
  interval: string,
  startTime: number,
  endTime: number,
  market: BinanceMarket,
): Promise<Candle[]> {
  const bases = BINANCE_API_BASES[market];
  const klinePath = market === "futures" ? "/fapi/v1/klines" : "/api/v3/klines";
  let res: Response | null = null;
  for (let attempt = 0; attempt < bases.length; attempt++) {
    const url = new URL(`${bases[attempt]}${klinePath}`);
    url.searchParams.set("symbol", symbol);
    url.searchParams.set("interval", interval);
    url.searchParams.set("startTime", String(startTime));
    url.searchParams.set("endTime", String(endTime));
    url.searchParams.set("limit", "1000");
    try {
      res = await fetch(url.toString(), { signal: AbortSignal.timeout(20_000) });
    } catch (error) {
      logger.debug({ err: error, base: bases[attempt], market }, "Binance REST endpoint failed; trying fallback");
      continue;
    }
    if (res.ok) break;
    if (res.status !== 429 && res.status < 500) return [];
    await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** attempt));
  }
  if (!res?.ok) return [];
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

async function mapConcurrent<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await worker(items[index]);
    }
  });
  await Promise.all(runners);
  return results;
}

export function intervalToMs(interval: string): number {
  const unit  = interval.slice(-1);
  const value = parseInt(interval.slice(0, -1), 10) || 1;
  switch (unit) {
    case "s": return value * 1_000;
    case "m": return value * 60_000;
    case "h": return value * 3_600_000;
    case "d": return value * 86_400_000;
    case "w": return value * 7 * 86_400_000;
    case "M": return value * 30 * 86_400_000;
    default:  return 60_000;
  }
}

export function aggregateFixedInterval(candles: Candle[], targetMs: number): Candle[] {
  const buckets = new Map<number, Candle>();
  for (const candle of candles) {
    const bucketOpen = Math.floor(candle.openTime / targetMs) * targetMs;
    const existing = buckets.get(bucketOpen);
    if (!existing) {
      buckets.set(bucketOpen, {
        ...candle,
        openTime: bucketOpen,
        closeTime: bucketOpen + targetMs - 1,
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

async function fetchOneSecondDay(symbol: string, day: string): Promise<Candle[]> {
  const key = `spot:${symbol}:${day}`;
  let entry = oneSecondDays.get(key);
  if (entry?.complete) return entry.candles;
  // Coalesce the three second-frame consumers and avoid tail polling faster
  // than the source can materially change.
  if (entry && Date.now() - entry.updatedAt < 2_000) return entry.candles;

  if (!entry?.checkedVision) {
    const zipped = await fetchZip(`${VISION_BASES.spot}/daily/klines/${symbol}/1s/${symbol}-1s-${day}.zip`);
    if (zipped?.length) {
      entry = { candles: zipped, complete: true, checkedVision: true, updatedAt: Date.now() };
      oneSecondDays.set(key, entry);
      pruneOneSecondDays();
      return zipped;
    }
    entry = { candles: entry?.candles ?? [], complete: false, checkedVision: true, updatedAt: 0 };
  }

  const dayStart = new Date(`${day}T00:00:00.000Z`).getTime();
  const dayEnd = dayStart + 86_400_000 - 1;
  const fetchEnd = Math.min(dayEnd, Date.now());
  const last = entry.candles.at(-1);
  const fetchStart = Math.max(dayStart, last ? last.closeTime + 1 : dayStart);
  if (fetchStart <= fetchEnd) {
    const tail = await fetchRestGap(symbol, "1s", fetchStart, fetchEnd, "spot");
    entry.candles = normalizeCandles([...entry.candles, ...tail], dayStart, dayEnd);
  }
  entry.complete = fetchEnd >= dayEnd;
  entry.updatedAt = Date.now();
  oneSecondDays.set(key, entry);
  pruneOneSecondDays();
  return entry.candles;
}

function pruneOneSecondDays(): void {
  while (oneSecondDays.size > 12) {
    const oldest = [...oneSecondDays.keys()].sort((a, b) => a.localeCompare(b))[0];
    if (!oldest) break;
    oneSecondDays.delete(oldest);
  }
}

/**
 * Fetch a large bounded 1-second window without asking REST for the entire
 * range. Published UTC days come from Binance Data Vision ZIPs; only missing
 * days (normally the live tail) fall back to the official market-data REST
 * endpoint. This keeps 5s/15s/30s warm-up history exact and tractable.
 */
async function fetchOneSecondWindow(
  symbol: string,
  limit: number,
  endTime: number,
): Promise<Candle[]> {
  const safeLimit = Math.max(100, Math.min(limit, 800_000));
  const alignedEnd = Math.min(endTime, Date.now());
  const startTime = alignedEnd - safeLimit * 1_000;
  const key = `one-second-window:${symbol}:${safeLimit}:${Math.floor(alignedEnd / 2_000)}`;
  const pending = inflight.get(key);
  if (pending) return pending;

  const request = (async () => {
    const days = daysBetween(new Date(startTime), new Date(alignedEnd));
    const dailyResults = await mapConcurrent(days, 4, (day) => fetchOneSecondDay(symbol, day));
    return normalizeCandles(dailyResults.flat(), startTime, alignedEnd).slice(-safeLimit);
  })().finally(() => inflight.delete(key));

  inflight.set(key, request);
  return request;
}

function aggregateQuarterly(candles: Candle[]): Candle[] {
  const buckets = new Map<number, Candle>();
  for (const candle of candles) {
    const date = new Date(candle.openTime);
    const quarterMonth = Math.floor(date.getUTCMonth() / 3) * 3;
    const bucketOpen = Date.UTC(date.getUTCFullYear(), quarterMonth, 1);
    const bucketClose = Date.UTC(date.getUTCFullYear(), quarterMonth + 3, 1) - 1;
    const existing = buckets.get(bucketOpen);
    if (!existing) {
      buckets.set(bucketOpen, { ...candle, openTime: bucketOpen, closeTime: bucketClose });
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
  if (aggregated.length) {
    const firstDate = new Date(candles[0].openTime);
    if (firstDate.getUTCMonth() % 3 !== 0) aggregated.shift();
  }
  return aggregated;
}

/** Native daily, weekly, and monthly candles must begin on calendar boundaries.
 * This prevents a fallback payload of hourly bars from ever being rendered as
 * a higher timeframe chart. Binance weekly candles begin Monday at 00:00 UTC. */
function matchesNativeTimeframe(candle: Candle, interval: string): boolean {
  if (!['1d', '1w', '1M'].includes(interval)) return true;
  const date = new Date(candle.openTime);
  if (date.getUTCHours() !== 0 || date.getUTCMinutes() !== 0 || date.getUTCSeconds() !== 0) return false;
  if (interval === '1w') return date.getUTCDay() === 1;
  if (interval === '1M') return date.getUTCDate() === 1;
  return true;
}

/** Fetch native Binance candles or build exact calendar/fixed custom frames. */
export async function fetchChartWindow(
  symbol: string,
  interval: string,
  limit: number,
  endTime = Date.now(),
  market: BinanceMarket = "spot",
): Promise<Candle[]> {
  if (["5s", "15s", "30s"].includes(interval)) {
    if (market === "futures") return [];
    const targetMs = intervalToMs(interval);
    const secondsPerBar = targetMs / 1_000;
    const rawLimit = limit * secondsPerBar + secondsPerBar * 2;
    const base = await fetchOneSecondWindow(symbol, rawLimit, endTime);
    return aggregateFixedInterval(base, targetMs).slice(-limit);
  }
  if (interval === "2m") {
    const base = await fetchHistoricalWindow(symbol, "1m", limit * 2 + 4, endTime, market);
    return aggregateFixedInterval(base, 2 * 60_000).slice(-limit);
  }
  if (interval === "45m") {
    const base = await fetchHistoricalWindow(symbol, "15m", limit * 3 + 6, endTime, market);
    return aggregateFixedInterval(base, 45 * 60_000).slice(-limit);
  }
  if (interval === "3M") {
    // Do not request an artificial thousand-month range. Binance may answer
    // that very old range with an empty page; 360 months is more than enough
    // for all listed spot pairs and produces genuine calendar quarters.
    const base = await fetchHistoricalWindow(symbol, "1M", Math.min(limit * 3 + 6, 360), endTime, market);
    return aggregateQuarterly(base).slice(-limit);
  }
  const native = await fetchHistoricalWindow(symbol, interval, limit, endTime, market);
  const verified = native.filter((candle) => matchesNativeTimeframe(candle, interval));
  if (verified.length !== native.length) {
    logger.warn({ symbol, interval, rejected: native.length - verified.length }, "Rejected misaligned higher-timeframe candles");
  }
  return verified;
}

/** Fetch the entire REST gap in parallel pages */
async function fetchRestGap(
  symbol: string,
  interval: string,
  gapStart: number,
  gapEnd: number,
  market: BinanceMarket,
): Promise<Candle[]> {
  const barMs   = intervalToMs(interval);
  const gapBars = Math.ceil((gapEnd - gapStart) / barMs);
  const pages   = Math.max(1, Math.ceil(gapBars / 1000));

  // Build page boundaries upfront and fire them all in parallel
  const pagesToFetch: Array<{ start: number; end: number }> = [];
  for (let p = 0; p < pages; p++) {
    const pStart = gapStart + p * 1000 * barMs;
    const pEnd   = Math.min(gapStart + (p + 1) * 1000 * barMs - 1, gapEnd);
    pagesToFetch.push({ start: pStart, end: pEnd });
  }

  const results = await mapConcurrent(
    pagesToFetch,
    4,
    (page) => restPage(symbol, interval, page.start, page.end, market),
  );
  return results.flat();
}

function isValidCandle(candle: Candle): boolean {
  const open = Number(candle.open);
  const high = Number(candle.high);
  const low = Number(candle.low);
  const close = Number(candle.close);
  const volume = Number(candle.volume);
  return Number.isFinite(candle.openTime)
    && Number.isFinite(candle.closeTime)
    && Number.isFinite(open)
    && Number.isFinite(high)
    && Number.isFinite(low)
    && Number.isFinite(close)
    && Number.isFinite(volume)
    && candle.openTime >= 0
    && candle.closeTime >= candle.openTime
    && open > 0
    && high >= Math.max(open, close)
    && low > 0
    && low <= Math.min(open, close)
    && volume >= 0;
}

function normalizeCandles(candles: Candle[], startTime: number, endTime: number): Candle[] {
  candles.sort((a, b) => a.openTime - b.openTime);
  const seen = new Set<number>();
  return candles.filter((c) => {
    if (!isValidCandle(c) || c.openTime < startTime || c.openTime > endTime || seen.has(c.openTime)) return false;
    seen.add(c.openTime);
    return true;
  });
}

function findMissingRanges(candles: Candle[], intervalMs: number): Array<{ start: number; end: number }> {
  const gaps: Array<{ start: number; end: number }> = [];
  for (let index = 1; index < candles.length; index++) {
    const previous = candles[index - 1].openTime;
    const current = candles[index].openTime;
    // A small tolerance avoids false positives around calendar-based frames.
    if (current - previous > intervalMs * 1.5) {
      gaps.push({ start: previous + intervalMs, end: current - 1 });
    }
  }
  return gaps;
}

/** Fetch a bounded chart window. Older windows are requested lazily as the
 * user scrolls left, keeping the first paint fast even on one-minute data. */
export async function fetchHistoricalWindow(
  symbol: string,
  interval: string,
  limit: number,
  endTime = Date.now(),
  market: BinanceMarket = "spot",
): Promise<Candle[]> {
  const safeLimit = Math.max(100, Math.min(limit, 30_000));
  const barMs = intervalToMs(interval);
  const alignedEnd = Math.min(endTime, Date.now());
  const startTime = alignedEnd - safeLimit * barMs;
  const key = `window:${market}:${symbol}:${interval}:${safeLimit}:${Math.floor(alignedEnd / barMs)}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  const pending = inflight.get(key);
  if (pending) return pending;

  const request = fetchRestGap(symbol, interval, startTime, alignedEnd, market)
    .then(async (candles) => {
      let normalized = normalizeCandles(candles, startTime, alignedEnd);
      const gaps = findMissingRanges(normalized, barMs);

      // Retry only the missing ranges. This catches transient REST pagination
      // failures and prevents broken gaps or malformed OHLC bars from reaching
      // the chart. Binance can legitimately omit unsupported symbols, so a
      // remaining gap is logged rather than fabricated with synthetic candles.
      if (gaps.length) {
        const repairs = await mapConcurrent(
          gaps.slice(0, 32),
          4,
          (gap) => fetchRestGap(symbol, interval, gap.start, gap.end, market),
        );
        normalized = normalizeCandles([...normalized, ...repairs.flat()], startTime, alignedEnd);
        const unresolved = findMissingRanges(normalized, barMs);
        if (unresolved.length) {
          logger.warn({ symbol, interval, gaps: unresolved.length }, "Historical candle gaps remain after repair");
        }
      }

      const window = normalized.slice(-safeLimit);
      cacheSet(key, window);
      return window;
    })
    .finally(() => inflight.delete(key));
  inflight.set(key, request);
  return request;
}

// ── Main export ───────────────────────────────────────────────────────────────

async function loadHistoricalKlines(
  symbol: string,
  interval: string,
  days: number,
  market: BinanceMarket,
): Promise<Candle[]> {
  const cacheKey = `${market}:${symbol}:${interval}:${days}`;
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
  const monthResults = await mapConcurrent(
    months,
    6,
    (month) => fetchZip(`${VISION_BASES[market]}/monthly/klines/${symbol}/${interval}/${symbol}-${interval}-${month}.zip`),
  );

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
    const dailyResults = await mapConcurrent(
      missDays,
      8,
      (day) => fetchZip(`${VISION_BASES[market]}/daily/klines/${symbol}/${interval}/${symbol}-${interval}-${day}.zip`),
    );
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
      const tail = await fetchRestGap(symbol, interval, gapStart, now, market);
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

export function fetchHistoricalKlines(
  symbol: string,
  interval: string,
  days: number,
  market: BinanceMarket = "spot",
): Promise<Candle[]> {
  const key = `${market}:${symbol}:${interval}:${days}`;
  const cached = cacheGet(key);
  if (cached) return Promise.resolve(cached);
  const pending = inflight.get(key);
  if (pending) return pending;
  const request = loadHistoricalKlines(symbol, interval, days, market)
    .finally(() => inflight.delete(key));
  inflight.set(key, request);
  return request;
}
