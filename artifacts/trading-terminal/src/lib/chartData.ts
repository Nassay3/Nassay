import { useInfiniteQuery } from '@tanstack/react-query';

export interface ChartPage {
  symbol: string;
  interval: string;
  candles: any[];
  indicators: any;
  hasMore: boolean;
  nextEndTime: number;
  timing: { fetchMs: number; calculateMs: number };
}

const PAGE_SIZE = 2_500;

async function fetchChartPage(
  symbol: string,
  interval: string,
  endTime?: number,
  signal?: AbortSignal,
): Promise<ChartPage> {
  const params = new URLSearchParams({ symbol, interval, limit: String(PAGE_SIZE) });
  if (endTime) params.set('endTime', String(endTime));
  const response = await fetch(`/api/market/chart?${params.toString()}`, { signal });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Chart request failed (${response.status})`);
  }
  return response.json();
}

export function useChartData(symbol: string, interval: string) {
  return useInfiniteQuery({
    queryKey: ['market-chart', symbol, interval],
    queryFn: ({ pageParam, signal }) => fetchChartPage(symbol, interval, pageParam, signal),
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
  const uniqueCandles = candles.filter(
    (candle, index) => index === 0 || candle.openTime !== candles[index - 1].openTime,
  );
  const indicators = chronological.reduce<any>(
    (merged, page) => merged ? mergeValue(merged, page.indicators) : page.indicators,
    null,
  );
  return { candles: uniqueCandles, indicators };
}
