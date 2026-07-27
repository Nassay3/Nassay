import { useInfiniteQuery } from '@tanstack/react-query';
import type { MarketType } from '@/context/TradingContext';

export interface ChartPage {
  symbol: string;
  interval: string;
  market: MarketType;
  candles: any[];
  indicators: any;
  hasMore: boolean;
  nextEndTime: number;
  timing: { fetchMs: number; calculateMs: number };
}

const MAX_INITIAL_BARS = 20_000;
const TWO_WEEKS_MS = 14 * 24 * 60 * 60 * 1_000;
const HIGHER_TIMEFRAME_BARS: Partial<Record<string, number>> = {
  '1d': 730,  // about two years
  '1w': 260,  // about five years
  '1M': 120,  // about ten years
  '3M': 80,   // about twenty years
};

function intervalToMs(interval: string): number {
  const value = Number.parseInt(interval.slice(0, -1), 10) || 1;
  switch (interval.at(-1)) {
    case 's': return value * 1_000;
    case 'm': return value * 60_000;
    case 'h': return value * 60 * 60 * 1_000;
    case 'd': return value * 24 * 60 * 60 * 1_000;
    case 'w': return value * 7 * 24 * 60 * 60 * 1_000;
    case 'M': return value * 30 * 24 * 60 * 60 * 1_000;
    default: return 60 * 60 * 1_000;
  }
}

/** Start with up to 14 days, so one-minute charts do not silently start with
 * only the most recent day or two. The cap keeps second charts responsive. */
function pageSizeForInterval(interval: string): number {
  const higherTimeframeBars = HIGHER_TIMEFRAME_BARS[interval];
  if (higherTimeframeBars) return higherTimeframeBars;
  const twoWeekBars = Math.ceil(TWO_WEEKS_MS / intervalToMs(interval));
  return Math.max(2_500, Math.min(MAX_INITIAL_BARS, twoWeekBars));
}

async function fetchChartPage(
  symbol: string,
  interval: string,
  market: MarketType,
  endTime?: number,
  signal?: AbortSignal,
): Promise<ChartPage> {
  const params = new URLSearchParams({ symbol, interval, market, limit: String(pageSizeForInterval(interval)) });
  if (endTime) params.set('endTime', String(endTime));
  const response = await fetch(`/api/market/chart?${params.toString()}`, { signal });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Chart request failed (${response.status})`);
  }
  return response.json();
}

export function useChartData(symbol: string, interval: string, market: MarketType) {
  return useInfiniteQuery({
    queryKey: ['market-chart', market, symbol, interval],
    queryFn: ({ pageParam, signal }) => fetchChartPage(symbol, interval, market, pageParam, signal),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => lastPage.hasMore ? lastPage.nextEndTime : undefined,
    staleTime: 60_000,
    gcTime: 15 * 60_000,
    refetchOnWindowFocus: false,
    retry: 2,
  });
}

function isPointArray(value: unknown[]): boolean {
  const first = value[0];
  return Boolean(first && typeof first === 'object' && 'time' in first && 'value' in first);
}

function mergePoints(older: any[], newer: any[]): any[] {
  if (!older.length) return newer;
  if (!newer.length) return older;
  const boundary = newer[0].time;
  return [...older.filter((point) => point.time < boundary), ...newer];
}

function mergeValue(older: any, newer: any): any {
  if (older == null) return newer;
  if (newer == null) return older;
  if (Array.isArray(older) && Array.isArray(newer)) {
    if (isPointArray(older) || isPointArray(newer)) return mergePoints(older, newer);
    if (newer.every((item) => item && typeof item === 'object' && 'name' in item)) {
      const oldByName = new Map(older.map((item) => [item.name, item]));
      return newer.map((item) => mergeValue(oldByName.get(item.name), item));
    }
    return newer.map((item, index) => mergeValue(older[index], item));
  }
  if (typeof older === 'object' && typeof newer === 'object') {
    const result: Record<string, any> = { ...older };
    for (const [key, value] of Object.entries(newer)) {
      result[key] = mergeValue(older[key], value);
    }
    return result;
  }
  return newer;
}

export function mergeChartPages(pages: ChartPage[]) {
  const chronological = [...pages].reverse();
  const candles = chronological.flatMap((page) => page.candles);
  const byOpenTime = new Map<number, any>();
  for (const candle of candles) {
    if (Number.isFinite(Number(candle?.openTime)) && !byOpenTime.has(candle.openTime)) {
      byOpenTime.set(candle.openTime, candle);
    }
  }
  const uniqueCandles = [...byOpenTime.values()].sort((a, b) => a.openTime - b.openTime);
  const indicators = chronological.reduce<any>(
    (merged, page) => merged ? mergeValue(merged, page.indicators) : page.indicators,
    null,
  );
  return { candles: uniqueCandles, indicators };
}
