import { Fragment, useEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from 'react';
import {
  createChart, ColorType, IChartApi, ISeriesApi,
  Time, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries, LineType, CrosshairMode,
} from 'lightweight-charts';
import {
  useTradingStore, Interval, INTERVAL_LABELS, DEFAULT_INDICATOR_SETTINGS,
  isVisibleForInterval, SubPane, IndicatorSetting, IndicatorSettings, CandleStyle, MarketType,
} from '@/context/TradingContext';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { wsManager } from '@/lib/ws';
import { useChartData, mergeChartPages } from '@/lib/chartData';
import { ArrowDown, ArrowUp, Eye, EyeOff, Settings2, ChevronDown, ChevronRight, GripVertical, PanelLeft, SlidersHorizontal, LoaderCircle, Database, ChevronsRight, Maximize2, Minimize2, RotateCcw, ShieldCheck, TriangleAlert } from 'lucide-react';

const IndicatorSettingsModal = lazy(() => import('./IndicatorSettingsModal'));

// ── Series helpers ────────────────────────────────────────────────────────────

function makeLine(
  chart: IChartApi,
  color: string,
  lineWidth: 1 | 2 | 3 = 1,
  lineStyle: 0 | 1 | 2 | 3 = 0,
  visible = true,
  lineType: LineType = LineType.Simple,
): ISeriesApi<'Line'> {
  return chart.addSeries(LineSeries, {
    color,
    lineWidth,
    lineStyle,
    lineType,
    visible,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    priceLineVisible: false,
  });
}

function makeArea(
  chart: IChartApi,
  color: string,
  lineWidth: 1 | 2 | 3 = 1,
  lineStyle: 0 | 1 | 2 | 3 = 0,
  visible = true,
): ISeriesApi<'Area'> {
  return chart.addSeries(AreaSeries, {
    lineColor: color,
    topColor: color,
    bottomColor: colorWithOpacity(color, 0.12),
    lineWidth,
    lineStyle,
    visible,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    priceLineVisible: false,
  });
}

function colorWithOpacity(color: string, opacity: number): string {
  const alpha = Math.max(0, Math.min(1, opacity));
  const hex = color.replace('#', '');
  if (/^[\da-f]{3}$/i.test(hex)) {
    const expanded = hex.split('').map((part) => part + part).join('');
    return colorWithOpacity(`#${expanded}`, alpha);
  }
  if (/^[\da-f]{6}$/i.test(hex)) {
    const red = Number.parseInt(hex.slice(0, 2), 16);
    const green = Number.parseInt(hex.slice(2, 4), 16);
    const blue = Number.parseInt(hex.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }
  return color;
}

function makeHistogram(
  chart: IChartApi,
  color: string,
  visible = true,
): ISeriesApi<'Histogram'> {
  return chart.addSeries(HistogramSeries, {
    color,
    visible,
    priceLineVisible: false,
    lastValueVisible: true,
  });
}

function setLineData(series: ISeriesApi<any>, pts: { time: number; value: number | null; color?: string }[], preservePointColors = true) {
  series.setData(
    pts
      .map(p => p.value !== null && Number.isFinite(p.value)
        ? ({ time: (p.time / 1000) as Time, value: p.value, ...(preservePointColors && p.color ? { color: p.color } : {}) })
        : ({ time: (p.time / 1000) as Time })),
  );
}

function plotTypeLineStyle(plotType: string): 0 | 1 | 2 | 3 {
  if (plotType.includes('broken')) return 1;
  if (plotType === 'cross') return 2;
  return 0;
}

function plotTypeLineType(plotType: string): LineType {
  if (plotType.startsWith('step')) return LineType.WithSteps;
  return LineType.Simple;
}

function plotTypeSeriesKind(plotType: string): 'Line' | 'Area' | 'Histogram' {
  if (plotType === 'histogram' || plotType === 'columns') return 'Histogram';
  if (plotType === 'area' || plotType === 'area-broken') return 'Area';
  return 'Line';
}

function seriesMatchesPlotType(series: ISeriesApi<any>, plotType: string): boolean {
  return series.seriesType() === plotTypeSeriesKind(plotType);
}

function createSeriesForPlotType(
  chart: IChartApi,
  plotType: string,
  color: string,
  lineWidth: 1 | 2 | 3,
  lineStyle: 0 | 1 | 2 | 3,
  visible: boolean,
): ISeriesApi<any> {
  const kind = plotTypeSeriesKind(plotType);
  if (kind === 'Histogram') return makeHistogram(chart, color, visible);
  if (kind === 'Area') return makeArea(chart, color, lineWidth, lineStyle, visible);
  const effectiveStyle = plotType.includes('broken') || plotType === 'cross'
    ? plotTypeLineStyle(plotType)
    : lineStyle;
  const series = makeLine(chart, color, lineWidth, effectiveStyle, visible, plotTypeLineType(plotType));
  if (plotType === 'circles') series.applyOptions({ lineVisible: false, pointMarkersVisible: true, pointMarkersRadius: lineWidth });
  return series;
}

function subChartBase(container: HTMLDivElement) {
  return createChart(container, {
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: '#07080b' }, textColor: '#8f96a3', fontSize: 10, fontFamily: 'Inter, ui-sans-serif, system-ui' },
    grid: { vertLines: { color: '#12141a' }, horzLines: { color: '#12141a' } },
    timeScale: {
      visible: false,
      rightOffset: 10,
      barSpacing: 8,
      minBarSpacing: 0.5,
      lockVisibleTimeRangeOnResize: true,
    },
    rightPriceScale: {
      visible: true,
      autoScale: true,
      alignLabels: true,
      borderVisible: true,
      borderColor: '#252832',
      ticksVisible: true,
      entireTextOnly: true,
      scaleMargins: { top: 0.1, bottom: 0.1 },
      minimumWidth: 72,
    },
    crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#758096', style: 3 }, horzLine: { color: '#758096', style: 3 } },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
    handleScale: { axisPressedMouseMove: true, axisDoubleClickReset: true, mouseWheel: true, pinch: true },
    kineticScroll: { mouse: true, touch: true },
  });
}

interface CandleQuality {
  candles: any[];
  rejected: number;
  gaps: number;
  coverageMs: number;
}

interface SavedChartView {
  from: number;
  to: number;
}

export interface RawChartCandle {
  openTime: number;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume: string | number;
}

interface PaneCrosshairRegistration {
  chart: IChartApi;
  series: ISeriesApi<any>;
  valueAtTime: (time: number) => number | null;
}

type RegisterPaneCrosshair = (paneId: string, registration: PaneCrosshairRegistration | null) => void;
type PaneCrosshairMove = (paneId: string, time: Time | null) => void;

function numericChartTime(time: Time | undefined | null): number | null {
  return typeof time === 'number' && Number.isFinite(time) ? Number(time) : null;
}

function valueLookup(points: Array<{ time: number; value: number | null }> | undefined): (time: number) => number | null {
  const indexed = new Map<number, number>();
  for (const point of points ?? []) {
    const time = Number(point.time) / 1000;
    const value = Number(point.value);
    if (Number.isFinite(time) && point.value !== null && Number.isFinite(value)) indexed.set(time, value);
  }
  return (time) => indexed.get(time) ?? null;
}

const CANDLE_STYLE_LABELS: Record<CandleStyle, { ar: string; en: string }> = {
  candles: { ar: 'شموع يابانية', en: 'Candles' },
  hollow: { ar: 'شموع مجوفة', en: 'Hollow candles' },
  'heikin-ashi': { ar: 'هايكين آشي', en: 'Heikin Ashi' },
};

function buildSingleCandlePoint(
  candle: RawChartCandle,
  style: CandleStyle,
  previousRealClose: number | null,
  previousDisplay: { open: number; close: number } | null,
): any {
  const realOpen = Number(candle.open);
  const realHigh = Number(candle.high);
  const realLow = Number(candle.low);
  const realClose = Number(candle.close);
  let open = realOpen;
  let high = realHigh;
  let low = realLow;
  let close = realClose;

  if (style === 'heikin-ashi') {
    close = (realOpen + realHigh + realLow + realClose) / 4;
    open = previousDisplay
      ? (previousDisplay.open + previousDisplay.close) / 2
      : (realOpen + realClose) / 2;
    high = Math.max(realHigh, open, close);
    low = Math.min(realLow, open, close);
  }

  const bullish = close >= open;
  const trendUp = previousRealClose === null ? bullish : realClose >= previousRealClose;
  const trendColor = trendUp ? '#089981' : '#f23645';

  if (style === 'hollow') {
    return {
      time: (Number(candle.openTime) / 1000) as Time,
      open, high, low, close,
      color: bullish ? 'rgba(0,0,0,0)' : trendColor,
      borderColor: trendColor,
      wickColor: trendColor,
    };
  }

  const color = bullish ? '#089981' : '#f23645';
  return {
    time: (Number(candle.openTime) / 1000) as Time,
    open, high, low, close,
    color,
    borderColor: color,
    wickColor: color,
  };
}

export function buildCandleSeriesData(candles: RawChartCandle[], style: CandleStyle): any[] {
  const output: any[] = [];
  for (let index = 0; index < candles.length; index++) {
    output.push(buildSingleCandlePoint(
      candles[index],
      style,
      index > 0 ? Number(candles[index - 1].close) : null,
      index > 0 ? output[index - 1] : null,
    ));
  }
  return output;
}

function CandleStyleGlyph({ style }: { style: CandleStyle }) {
  const hollow = style === 'hollow';
  return (
    <span className="relative block h-4 w-5 shrink-0" aria-hidden="true">
      <span className="absolute left-[4px] top-0 h-4 w-px bg-[#089981]" />
      <span className={`absolute left-[1px] top-[4px] h-[7px] w-[7px] border border-[#089981] ${hollow ? 'bg-[#101116]' : 'bg-[#089981]'}`} />
      <span className="absolute right-[3px] top-[1px] h-3.5 w-px bg-[#f23645]" />
      <span className="absolute right-0 top-[3px] h-[8px] w-[7px] border border-[#f23645] bg-[#f23645]" />
    </span>
  );
}

function chartViewStorageKey(market: MarketType, symbol: string, interval: string): string {
  // v2 intentionally discards ranges saved while stale cross-timeframe VWMA
  // series could distort the logical scale.
  return `terminal_chart_view_v3:${market}:${symbol}:${interval}`;
}

function readSavedChartView(market: MarketType, symbol: string, interval: string): SavedChartView | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(chartViewStorageKey(market, symbol, interval)) ?? 'null');
    if (Number.isFinite(parsed?.from) && Number.isFinite(parsed?.to) && parsed.from < parsed.to) {
      return parsed;
    }
  } catch {
    // Invalid or legacy chart state should never prevent the chart from loading.
  }
  return null;
}

function writeSavedChartView(market: MarketType, symbol: string, interval: string, range: SavedChartView): void {
  try {
    localStorage.setItem(chartViewStorageKey(market, symbol, interval), JSON.stringify(range));
  } catch {
    // Browsers may deny storage in private/locked-down contexts; chart use remains unaffected.
  }
}

function chartIntervalToMs(value: string): number {
  const size = Number.parseInt(value.slice(0, -1), 10) || 1;
  switch (value.at(-1)) {
    case 's': return size * 1_000;
    case 'm': return size * 60_000;
    case 'h': return size * 3_600_000;
    case 'd': return size * 86_400_000;
    case 'w': return size * 7 * 86_400_000;
    case 'M': return size * 30 * 86_400_000;
    default: return 60_000;
  }
}

function preferredVisibleBars(interval: string): number {
  switch (interval) {
    case '1d': return 120;
    case '1w': return 80;
    case '1M': return 60;
    case '3M': return 36;
    case '12h': return 150;
    case '6h':
    case '4h': return 180;
    default: return 180;
  }
}

function isAlignedToSelectedTimeframe(openTime: number, interval: string): boolean {
  if (!['1d', '1w', '1M', '3M'].includes(interval)) return true;
  const date = new Date(openTime);
  if (date.getUTCHours() !== 0 || date.getUTCMinutes() !== 0) return false;
  if (interval === '1w') return date.getUTCDay() === 1;
  if (interval === '1M') return date.getUTCDate() === 1;
  if (interval === '3M') return date.getUTCDate() === 1 && date.getUTCMonth() % 3 === 0;
  return true;
}

/** A second validation pass keeps a bad payload from distorting the visible
 * candle scale even if an upstream source ever returns an invalid OHLC bar. */
function inspectCandles(candidates: any[], interval: string): CandleQuality {
  const clean: any[] = [];
  const seen = new Set<number>();
  let rejected = 0;
  for (const candle of [...candidates].sort((a, b) => Number(a?.openTime) - Number(b?.openTime))) {
    const time = Number(candle?.openTime);
    const open = Number(candle?.open);
    const high = Number(candle?.high);
    const low = Number(candle?.low);
    const close = Number(candle?.close);
    const volume = Number(candle?.volume);
    const valid = Number.isFinite(time) && Number.isFinite(open) && Number.isFinite(high)
      && Number.isFinite(low) && Number.isFinite(close) && Number.isFinite(volume)
      && open > 0 && low > 0 && volume >= 0 && high >= Math.max(open, close) && low <= Math.min(open, close)
      && isAlignedToSelectedTimeframe(time, interval);
    if (!valid || seen.has(time)) {
      rejected++;
      continue;
    }
    seen.add(time);
    clean.push(candle);
  }

  const barMs = chartIntervalToMs(interval);
  let gaps = 0;
  for (let index = 1; index < clean.length; index++) {
    const delta = Number(clean[index].openTime) - Number(clean[index - 1].openTime);
    if (delta > barMs * 1.5) gaps += Math.max(1, Math.round(delta / barMs) - 1);
  }
  return {
    candles: clean,
    rejected,
    gaps,
    coverageMs: clean.length > 1 ? Number(clean.at(-1).openTime) - Number(clean[0].openTime) : 0,
  };
}

// ── Sidebar group definitions ─────────────────────────────────────────────────

interface IndicatorRow {
  key: string;
  label?: string;
  isBand?: boolean;
  dynamicPrefix?: string;
}
interface IndicatorGroup {
  label: string;
  rows: IndicatorRow[];
  settingKey?: string;
}

const INDICATOR_GROUPS: IndicatorGroup[] = [
  {
    label: 'Multi VWAP', rows: [
      { key: 'VWAP 21' }, { key: 'VWAP 48' }, { key: 'VWAP 84' },
      { key: 'VWAP 175' }, { key: 'VWAP 480' }, { key: 'VWAP 840' },
    ],
  },
  {
    label: 'Daily', rows: [
      { key: 'Daily VWAP' }, { key: 'Prev Daily VWAP' },
      { key: 'Daily VWAP Bands', label: '± Bands', isBand: true },
    ],
  },
  {
    label: 'Weekly', rows: [
      { key: 'Weekly VWAP' }, { key: 'Prev Weekly VWAP' },
      { key: 'Weekly VWAP Bands', label: '± Bands', isBand: true },
    ],
  },
  {
    label: 'Sessions', settingKey: 'Session VWAP', rows: [
      { key: 'Session Asia' },   { key: 'Session Asia Bands',   label: 'Asia ± Bands',   isBand: true },
      { key: 'Session London' }, { key: 'Session London Bands', label: 'London ± Bands', isBand: true },
      { key: 'Session NY' },     { key: 'Session NY Bands',     label: 'NY ± Bands',     isBand: true },
      { key: 'Session Daily' },  { key: 'Session Daily Bands',  label: 'Daily ± Bands',  isBand: true },
    ],
  },
  {
    label: 'VWMA Auto', settingKey: 'VWMA Auto', rows: [
      { key: '__vwma__', dynamicPrefix: 'VWMA' },
    ],
  },
  {
    label: 'VWMA MTF Map', settingKey: 'VWMA MTF', rows: [
      { key: '__mtf__', dynamicPrefix: 'VWMA MTF' },
    ],
  },
  {
    label: 'Sub-Panes', rows: [
      { key: 'Combined Signal' }, { key: 'Integrated Dashboard' }, { key: 'Dollar Volume' }, { key: 'Session Volume' },
      { key: 'Relative QV' },  { key: 'ZScore' },
    ],
  },
];

// ── Main component ────────────────────────────────────────────────────────────

export default function ChartPanel() {
  const {
    activeSymbol, interval, setInterval,
    marketType,
    candleStyle, setCandleStyle,
    indicatorSettings, toggleIndicator,
    paneOrder, setPaneOrder,
    sidebarOpen, setSidebarOpen,
  } = useTradingStore();

  const chartRootRef      = useRef<HTMLDivElement>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const [chartApi, setChartApi] = useState<IChartApi | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const seriesRefs = useRef({
    candle:    null as ISeriesApi<'Candlestick'> | null,
    lines:     new Map<string, ISeriesApi<any>>(),   // key → main line (Line/Area/Histogram)
    bandLines: new Map<string, ISeriesApi<any>[]>(), // bandKey → [upper,lower] × nBands
  });
  const seriesNameMap = useRef(new Map<ISeriesApi<any>, string>());

  const [hoveredValues, setHoveredValues]   = useState<Record<string, number>>({});
  const [hoveredCandle, setHoveredCandle]   = useState<{ open: number; high: number; low: number; close: number } | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem('terminal_indicator_groups_v1') ?? '{}');
    } catch {
      return {};
    }
  });
  const [settingsOpen, setSettingsOpen]   = useState(false);
  const [settingsTarget, setSettingsTarget] = useState<string | null>(null);
  const [dynamicKeys, setDynamicKeys]       = useState<{ vwma: string[]; mtf: string[] }>({ vwma: [], mtf: [] });
  const [dragTarget, setDragTarget] = useState<SubPane | null>(null);
  const dragPane = useRef<SubPane | null>(null);
  const fittedDataKey = useRef<string | null>(null);
  const crosshairFrame = useRef<number | null>(null);
  const viewSaveTimer = useRef<number | null>(null);
  const pendingHoveredValues = useRef<Record<string, number>>({});
  const pendingHoveredCandle = useRef<{ open: number; high: number; low: number; close: number } | null>(null);
  const liveCandlesRef = useRef<RawChartCandle[]>([]);
  const displayCandlesRef = useRef<any[]>([]);
  const mainCrosshairPricesRef = useRef(new Map<number, number>());
  const paneCrosshairsRef = useRef(new Map<string, PaneCrosshairRegistration>());
  const synchronizingCrosshairRef = useRef(false);

  const registerPaneCrosshair = useCallback<RegisterPaneCrosshair>((paneId, registration) => {
    if (registration) paneCrosshairsRef.current.set(paneId, registration);
    else paneCrosshairsRef.current.delete(paneId);
  }, []);

  const synchronizeCrosshairs = useCallback((time: Time | null, sourcePane: string) => {
    if (synchronizingCrosshairRef.current) return;
    synchronizingCrosshairRef.current = true;
    try {
      const numericTime = numericChartTime(time);
      if (numericTime === null || time === null) {
        if (sourcePane !== 'main') chartRef.current?.clearCrosshairPosition();
        paneCrosshairsRef.current.forEach((registration, paneId) => {
          if (paneId !== sourcePane) registration.chart.clearCrosshairPosition();
        });
        return;
      }

      if (sourcePane !== 'main') {
        const candleSeries = seriesRefs.current.candle;
        const price = mainCrosshairPricesRef.current.get(numericTime);
        if (candleSeries && price !== undefined) {
          chartRef.current?.setCrosshairPosition(price, time, candleSeries);
        } else {
          chartRef.current?.clearCrosshairPosition();
        }
      }

      paneCrosshairsRef.current.forEach((registration, paneId) => {
        if (paneId === sourcePane) return;
        const value = registration.valueAtTime(numericTime);
        if (value !== null && Number.isFinite(value)) {
          registration.chart.setCrosshairPosition(value, time, registration.series);
        } else {
          registration.chart.clearCrosshairPosition();
        }
      });
    } finally {
      synchronizingCrosshairRef.current = false;
    }
  }, []);

  const handlePaneCrosshairMove = useCallback<PaneCrosshairMove>((paneId, time) => {
    synchronizeCrosshairs(time, paneId);
  }, [synchronizeCrosshairs]);

  const updateLiveCandle = useCallback((incoming: RawChartCandle) => {
    const candleSeries = seriesRefs.current.candle;
    if (!candleSeries) return;
    const candles = liveCandlesRef.current;
    const display = displayCandlesRef.current;
    const incomingTime = Number(incoming.openTime);
    const lastTime = Number(candles.at(-1)?.openTime);
    if (candles.length && incomingTime < lastTime) return;

    const replacing = candles.length > 0 && incomingTime === lastTime;
    const index = replacing ? candles.length - 1 : candles.length;
    if (replacing) candles[index] = incoming;
    else candles.push(incoming);

    const point = buildSingleCandlePoint(
      incoming,
      candleStyle,
      index > 0 ? Number(candles[index - 1].close) : null,
      index > 0 ? display[index - 1] : null,
    );
    if (replacing) display[index] = point;
    else display.push(point);
    candleSeries.update(point);
    mainCrosshairPricesRef.current.set(Number(point.time), Number(point.close));
  }, [candleStyle]);

  const chartQuery = useChartData(activeSymbol, interval, marketType);
  const mergedData = useMemo(
    () => chartQuery.data ? mergeChartPages(chartQuery.data.pages) : null,
    [chartQuery.data],
  );
  const dataMatchesSelection = Boolean(
    chartQuery.data?.pages.length
    && chartQuery.data.pages.every((page) =>
      page.symbol === activeSymbol && page.interval === interval && page.market === marketType),
  );
  const selectedData = dataMatchesSelection ? mergedData : null;
  const candleQuality = useMemo(
    () => inspectCandles(selectedData?.candles ?? [], interval),
    [selectedData?.candles, interval],
  );
  const klinesData = useMemo(
    () => selectedData ? { candles: candleQuality.candles } : null,
    [selectedData, candleQuality],
  );
  const candleSeriesData = useMemo(
    () => buildCandleSeriesData((klinesData?.candles ?? []) as RawChartCandle[], candleStyle),
    [klinesData?.candles, candleStyle],
  );
  const vwapData = selectedData?.indicators;

  useEffect(() => {
    try {
      localStorage.setItem('terminal_indicator_groups_v1', JSON.stringify(expandedGroups));
    } catch {
      // Keep the chart usable even when browser storage is unavailable.
    }
  }, [expandedGroups]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === chartRootRef.current);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  // ── Init main chart ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = createChart(chartContainerRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: '#07080b' }, textColor: '#8f96a3', fontSize: 11, fontFamily: 'Inter, ui-sans-serif, system-ui' },
      grid: { vertLines: { color: '#12141a' }, horzLines: { color: '#12141a' } },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#252832',
        rightOffset: 10,
        barSpacing: 8,
        minBarSpacing: 0.5,
        shiftVisibleRangeOnNewBar: true,
      },
      rightPriceScale: {
        visible: true,
        autoScale: true,
        alignLabels: true,
        borderVisible: true,
        borderColor: '#252832',
        ticksVisible: true,
        entireTextOnly: true,
        scaleMargins: { top: 0.08, bottom: 0.16 },
        minimumWidth: 72,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#758096', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
        horzLine: { color: '#758096', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, axisDoubleClickReset: true, mouseWheel: true, pinch: true },
      kineticScroll: { mouse: true, touch: true },
    });
    chartRef.current = chart;
    setChartApi(chart);

    seriesRefs.current.candle = chart.addSeries(CandlestickSeries, {
      upColor: '#089981', downColor: '#f23645',
      borderVisible: true, borderUpColor: '#089981', borderDownColor: '#f23645',
      wickUpColor: '#089981', wickDownColor: '#f23645',
      priceLineColor: '#2962ff',
    });
    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        pendingHoveredValues.current = {};
        pendingHoveredCandle.current = null;
      } else {
        const nv: Record<string, number> = {};
        seriesNameMap.current.forEach((name, series) => {
          const d = param.seriesData.get(series);
          if (d && 'value' in d) nv[name] = d.value as number;
        });
        pendingHoveredValues.current = nv;
        const candlePoint = seriesRefs.current.candle
          ? param.seriesData.get(seriesRefs.current.candle) as any
          : null;
        pendingHoveredCandle.current = candlePoint && 'open' in candlePoint
          ? { open: candlePoint.open, high: candlePoint.high, low: candlePoint.low, close: candlePoint.close }
          : null;
      }
      synchronizeCrosshairs(param.time ?? null, 'main');
      if (crosshairFrame.current === null) {
        crosshairFrame.current = window.requestAnimationFrame(() => {
          crosshairFrame.current = null;
          setHoveredValues(pendingHoveredValues.current);
          setHoveredCandle(pendingHoveredCandle.current);
        });
      }
    });

    return () => {
      if (crosshairFrame.current !== null) window.cancelAnimationFrame(crosshairFrame.current);
      chart.remove();
      chartRef.current = null;
      setChartApi(null);
      seriesRefs.current.candle = null;
      seriesRefs.current.lines.clear();
      seriesRefs.current.bandLines.clear();
      seriesNameMap.current.clear();
      paneCrosshairsRef.current.clear();
      mainCrosshairPricesRef.current.clear();
    };
  }, [synchronizeCrosshairs]);

  // A Lightweight Charts instance keeps every added series until it is
  // explicitly removed. Clear the previous selection immediately so hourly
  // VWMA points can never survive a switch to a daily or weekly chart.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    seriesRefs.current.candle?.setData([]);
    for (const series of seriesRefs.current.lines.values()) {
      try { chart.removeSeries(series); } catch {}
    }
    for (const seriesList of seriesRefs.current.bandLines.values()) {
      for (const series of seriesList) {
        try { chart.removeSeries(series); } catch {}
      }
    }
    seriesRefs.current.lines.clear();
    seriesRefs.current.bandLines.clear();
    seriesNameMap.current.clear();
    liveCandlesRef.current = [];
    displayCandlesRef.current = [];
    mainCrosshairPricesRef.current.clear();
    setDynamicKeys({ vwma: [], mtf: [] });
    setHoveredValues({});
    setHoveredCandle(null);
  }, [activeSymbol, interval, marketType]);

  useEffect(() => {
    const calendarFrame = ['1d', '1w', '1M', '3M'].includes(interval);
    chartRef.current?.timeScale().applyOptions({
      // Daily and higher frames must display calendar dates only. Leaving
      // timeVisible enabled is what makes weekly/monthly charts show noisy
      // hourly-looking labels despite having correctly aggregated candles.
      timeVisible: !calendarFrame,
      secondsVisible: interval.endsWith('s'),
      barSpacing: ['1w', '1M', '3M'].includes(interval) ? 11 : 8,
      minBarSpacing: ['1w', '1M', '3M'].includes(interval) ? 3 : 0.5,
    });
  }, [interval]);

  // ── Load candles ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!klinesData || !seriesRefs.current.candle) return;
    const dataKey = `${marketType}:${activeSymbol}:${interval}`;
    const preservedRange = fittedDataKey.current === dataKey
      ? chartRef.current?.timeScale().getVisibleRange()
      : null;
    liveCandlesRef.current = klinesData.candles.map((candle) => ({ ...candle }));
    displayCandlesRef.current = [...candleSeriesData];
    mainCrosshairPricesRef.current = new Map(
      candleSeriesData.map((point: any) => [Number(point.time), Number(point.close)]),
    );
    seriesRefs.current.candle.setData(displayCandlesRef.current);
    if (fittedDataKey.current !== dataKey && klinesData.candles.length) {
      const last = klinesData.candles.length - 1;
      const bars = preferredVisibleBars(interval);
      const firstTime = klinesData.candles[0].openTime / 1000;
      const lastTime = klinesData.candles[last].openTime / 1000;
      const savedView = readSavedChartView(marketType, activeSymbol, interval);
      if (savedView && savedView.to >= firstTime && savedView.from <= lastTime) {
        chartRef.current?.timeScale().setVisibleRange({
          from: savedView.from as Time,
          to: savedView.to as Time,
        });
      } else {
        chartRef.current?.timeScale().setVisibleLogicalRange({
          from: Math.max(0, last - bars),
          to: last + 10,
        });
      }
      fittedDataKey.current = dataKey;
    } else if (preservedRange) {
      chartRef.current?.timeScale().setVisibleRange(preservedRange);
    }
  }, [klinesData, candleSeriesData, activeSymbol, interval, candleStyle, marketType]);

  // Load older pages just before the user reaches the left edge.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const onRange = (range: { from: number; to: number } | null) => {
      if (
        range && range.from < 120 &&
        chartQuery.hasNextPage && !chartQuery.isFetchingNextPage
      ) {
        void chartQuery.fetchNextPage();
      }
      const visible = chart.timeScale().getVisibleRange();
      if (visible && typeof visible.from === 'number' && typeof visible.to === 'number') {
        if (viewSaveTimer.current !== null) window.clearTimeout(viewSaveTimer.current);
        viewSaveTimer.current = window.setTimeout(() => {
          writeSavedChartView(marketType, activeSymbol, interval, { from: visible.from as number, to: visible.to as number });
          viewSaveTimer.current = null;
        }, 250);
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
      if (viewSaveTimer.current !== null) {
        window.clearTimeout(viewSaveTimer.current);
        const visible = chart.timeScale().getVisibleRange();
        if (visible && typeof visible.from === 'number' && typeof visible.to === 'number') {
          writeSavedChartView(marketType, activeSymbol, interval, {
            from: visible.from as number,
            to: visible.to as number,
          });
        }
        viewSaveTimer.current = null;
      }
    };
  }, [chartQuery.fetchNextPage, chartQuery.hasNextPage, chartQuery.isFetchingNextPage, activeSymbol, interval, marketType]);

  // ── Load VWAP indicators ───────────────────────────────────────────────────
  useEffect(() => {
    if (!chartRef.current || !vwapData || !klinesData?.candles.length) return;
    const chart = chartRef.current;
    const { lines, bandLines } = seriesRefs.current;
    const activeLineKeys = new Set<string>();
    const activeBandKeys = new Set<string>();
    const candleTimes = new Set(klinesData.candles.map((candle) => Number(candle.openTime)));
    const clipToCurrentCandles = <T extends { time: number },>(values: T[]): T[] =>
      values.filter((point) => candleTimes.has(Number(point.time)));

    /** Upsert a single series and fill its data based on plot type */
    const syncLine = (
      key: string,
      data: { color: string; values: { time: number; value: number | null; color?: string }[] } | null | undefined,
      overrides?: { lineWidth?: 1|2|3; lineStyle?: 0|1|2|3 },
    ) => {
      if (!data?.values) return;
      activeLineKeys.add(key);
      const dynamicGroup = key.startsWith('VWMA ')
        ? (key.includes('[') ? 'VWMA MTF' : 'VWMA Auto')
        : null;
      const settingKey = dynamicGroup ?? key;
      const setting    = indicatorSettings[settingKey] ?? DEFAULT_INDICATOR_SETTINGS[settingKey];
      const tfVisible  = isVisibleForInterval(key, interval as Interval, setting);
      const sessionMaster = key.startsWith('Session ')
        ? indicatorSettings['Session VWAP'] ?? DEFAULT_INDICATOR_SETTINGS['Session VWAP']
        : undefined;
      const sessionMasterVisible = !sessionMaster
        || ((sessionMaster.visible ?? true) && isVisibleForInterval('Session VWAP', interval as Interval, sessionMaster));
      const visible    = sessionMasterVisible && (setting?.visible ?? true) && tfVisible;
      const plotType   = setting?.plotType ?? 'line';
      const color      = dynamicGroup ? data.color : (setting?.color ?? data.color);
      const displayColor = colorWithOpacity(color, (setting?.opacity ?? 100) / 100);
      const lineWidth  = overrides?.lineWidth ?? setting?.lineWidth ?? 1;
      const lineStyle  = overrides?.lineStyle ?? setting?.lineStyle ?? 0;
      const showLastValue = setting?.showLastValue ?? true;
      const showPriceLine = setting?.showPriceLine ?? false;

      let series = lines.get(key);
      const existingSeries = series;
      const needsRecreate = existingSeries && !seriesMatchesPlotType(existingSeries, plotType);
      if (needsRecreate) {
        try { chart.removeSeries(existingSeries); } catch {}
        lines.delete(key);
        seriesNameMap.current.delete(existingSeries);
        series = undefined;
      }

      if (!series) {
        series = createSeriesForPlotType(chart, plotType, displayColor, lineWidth, lineStyle, visible);
        lines.set(key, series);
        seriesNameMap.current.set(series, key);
      } else {
        const kind = plotTypeSeriesKind(plotType);
        if (kind === 'Histogram') series.applyOptions({ visible, color: displayColor, lastValueVisible: showLastValue, priceLineVisible: showPriceLine });
        else if (kind === 'Area') series.applyOptions({
          visible, lineColor: displayColor, topColor: displayColor, bottomColor: colorWithOpacity(displayColor, 0.12), lineWidth, lineStyle,
          lastValueVisible: showLastValue, priceLineVisible: showPriceLine,
        });
        else series.applyOptions({
          visible, color: displayColor, lineWidth,
          lineStyle: plotType.includes('broken') || plotType === 'cross' ? plotTypeLineStyle(plotType) : lineStyle,
          lineType: plotTypeLineType(plotType),
          lineVisible: plotType !== 'circles',
          pointMarkersVisible: plotType === 'circles',
          pointMarkersRadius: lineWidth,
          lastValueVisible: showLastValue,
          priceLineVisible: showPriceLine,
        });
      }
      series.applyOptions({ lastValueVisible: showLastValue, priceLineVisible: showPriceLine });
      const defaultColor = DEFAULT_INDICATOR_SETTINGS[settingKey]?.color;
      const preservePointColors = (!setting?.color || setting.color === defaultColor) && (setting?.opacity ?? 100) === 100;
      setLineData(series, clipToCurrentCandles(data.values), preservePointColors);
    };

    /** Upsert band lines (upper + lower) for a given bandKey */
    const syncBands = (
      bandKey: string,            // e.g. "Daily VWAP Bands", "Session Asia Bands"
      rawBands: { upper: { time: number; value: number | null }[]; lower: { time: number; value: number | null }[]; upperColor: string; lowerColor: string }[],
      parentKey: string,          // e.g. "Daily VWAP" — for TF visibility
    ) => {
      activeBandKeys.add(bandKey);
      // Remove old band series for this key
      const old = bandLines.get(bandKey);
      old?.forEach(s => { try { chart.removeSeries(s); } catch {} });
      bandLines.delete(bandKey);

      const defaultSetting = DEFAULT_INDICATOR_SETTINGS[bandKey];
      const setting  = indicatorSettings[bandKey] ?? defaultSetting;
      const tfOk     = isVisibleForInterval(bandKey, interval as Interval, setting);
      const sessionMaster = bandKey.startsWith('Session ')
        ? indicatorSettings['Session VWAP'] ?? DEFAULT_INDICATOR_SETTINGS['Session VWAP']
        : undefined;
      const sessionMasterVisible = !sessionMaster
        || ((sessionMaster.visible ?? true) && isVisibleForInterval('Session VWAP', interval as Interval, sessionMaster));
      const visible  = sessionMasterVisible && (setting?.visible ?? false) && tfOk;
      if (!rawBands.length) return;

      const newSeries: ISeriesApi<'Line'>[] = [];
      for (const band of rawBands) {
        const customColor = setting?.color && setting.color !== defaultSetting?.color;
        const uColor = colorWithOpacity(customColor ? setting.color : band.upperColor, (setting?.opacity ?? 100) / 100);
        const lColor = colorWithOpacity(customColor ? setting.color : band.lowerColor, (setting?.opacity ?? 100) / 100);
        const uStyle = setting?.lineStyle ?? 0;
        const width = setting?.lineWidth ?? 1;
        const u = makeLine(chart, uColor, width, uStyle, visible);
        const l = makeLine(chart, lColor, width, uStyle, visible);
        u.applyOptions({ lastValueVisible: setting?.showLastValue ?? true, priceLineVisible: setting?.showPriceLine ?? false });
        l.applyOptions({ lastValueVisible: setting?.showLastValue ?? true, priceLineVisible: setting?.showPriceLine ?? false });
        setLineData(u, clipToCurrentCandles(band.upper));
        setLineData(l, clipToCurrentCandles(band.lower));
        newSeries.push(u, l);
      }
      bandLines.set(bandKey, newSeries);
    };

    // Multi VWAP
    vwapData.multiPeriodVwaps.forEach((v: any) => syncLine(v.name, v));

    // Daily VWAP
    syncLine('Daily VWAP',      vwapData.dailyVwap.current);
    syncLine('Prev Daily VWAP', vwapData.dailyVwap.previous);
    syncBands('Daily VWAP Bands', vwapData.dailyVwap.bands, 'Daily VWAP');

    // Weekly VWAP
    syncLine('Weekly VWAP',      vwapData.weeklyVwap.current);
    syncLine('Prev Weekly VWAP', vwapData.weeklyVwap.previous);
    syncBands('Weekly VWAP Bands', vwapData.weeklyVwap.bands, 'Weekly VWAP');

    // Sessions
    vwapData.sessions.forEach((session: any) => {
      const lineKey = session.vwap.name;   // e.g. "Session Asia"
      const bandKey = lineKey + ' Bands';  // e.g. "Session Asia Bands"
      syncLine(lineKey, session.vwap);
      syncBands(bandKey, session.bands, lineKey);
    });

    // VWMA Auto
    const vwmaKeys: string[] = [];
    (vwapData.vwapUltra1 ?? []).forEach((line: any) => {
      syncLine(line.name, line, { lineWidth: indicatorSettings['VWMA Auto']?.lineWidth ?? 1 });
      vwmaKeys.push(line.name);
    });

    // VWMA MTF
    const mtfKeys: string[] = [];
    (vwapData.vwmaMtfMap ?? []).forEach((line: any) => {
      syncLine(line.name, line, { lineWidth: indicatorSettings['VWMA MTF']?.lineWidth ?? 1 });
      mtfKeys.push(line.name);
    });

    // Remove any series that existed on the previous payload but is not
    // defined for the current timeframe. This is especially important for
    // VWMA Auto/MTF because their period sets change between 1h, 1d and 1w.
    for (const [key, series] of [...lines.entries()]) {
      if (activeLineKeys.has(key)) continue;
      try { chart.removeSeries(series); } catch {}
      lines.delete(key);
      seriesNameMap.current.delete(series);
    }
    for (const [key, seriesList] of [...bandLines.entries()]) {
      if (activeBandKeys.has(key)) continue;
      for (const series of seriesList) {
        try { chart.removeSeries(series); } catch {}
      }
      bandLines.delete(key);
    }

    setDynamicKeys({ vwma: vwmaKeys, mtf: mtfKeys });

  }, [vwapData, klinesData, interval, indicatorSettings]);

  // ── WebSocket live feed ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!seriesRefs.current.candle) return;
    const unsub = wsManager.onMessage((msg) => {
      if (msg.e === 'kline' && msg.s === activeSymbol) {
        const k = msg.k;
        updateLiveCandle({
          openTime: Number(k.t),
          open: k.o, high: k.h, low: k.l, close: k.c, volume: k.v,
        });
      }
    });
    return () => { unsub(); };
  }, [activeSymbol, marketType, updateLiveCandle]);

  // Refresh the latest indicator point without reloading the historical pages.
  useEffect(() => {
    if (!vwapData) return;
    let stopped = false;
    let controller: AbortController | null = null;

    const updateLine = (line: any, expectedTime: number | null) => {
      const point = line?.values?.at(-1);
      const series = line?.name ? seriesRefs.current.lines.get(line.name) : null;
      if (series && point?.value != null && expectedTime !== null && Number(point.time) === expectedTime) {
        series.update({ time: (point.time / 1000) as Time, value: point.value });
      }
    };

    const refresh = async () => {
      if (stopped || document.visibilityState !== 'visible') return;
      controller = new AbortController();
      try {
        const params = new URLSearchParams({ symbol: activeSymbol, interval, market: marketType, limit: '2' });
        const response = await fetch(`/api/market/chart?${params}`, { signal: controller.signal });
        if (!response.ok || stopped) return;
        const payload = await response.json();
        const snapshot = payload.indicators;
        const latestCandle = payload.candles?.at(-1);
        const latestCandleTime = Number.isFinite(Number(latestCandle?.openTime))
          ? Number(latestCandle.openTime)
          : null;
        if (latestCandle) {
          updateLiveCandle(latestCandle);
        }
        snapshot.multiPeriodVwaps?.forEach((line: any) => updateLine(line, latestCandleTime));
        updateLine(snapshot.dailyVwap?.current, latestCandleTime);
        updateLine(snapshot.dailyVwap?.previous, latestCandleTime);
        updateLine(snapshot.weeklyVwap?.current, latestCandleTime);
        updateLine(snapshot.weeklyVwap?.previous, latestCandleTime);
        snapshot.sessions?.forEach((session: any) => updateLine(session.vwap, latestCandleTime));
        snapshot.vwapUltra1?.forEach((line: any) => updateLine(line, latestCandleTime));
        snapshot.vwmaMtfMap?.forEach((line: any) => updateLine(line, latestCandleTime));
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          // The historical query remains authoritative; a missed live refresh is harmless.
        }
      }
    };

    const timer = window.setInterval(refresh, 15_000);
    return () => {
      stopped = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [activeSymbol, interval, marketType, vwapData, updateLiveCandle]);

  // ── Drag-to-reorder sub-panes ─────────────────────────────────────────────
  const handleDragStart = useCallback((pane: SubPane) => {
    dragPane.current = pane;
    setDragTarget(null);
  }, []);
  const handleDragOver  = useCallback((e: React.DragEvent, target: SubPane) => {
    e.preventDefault();
    if (!dragPane.current || dragPane.current === target) return;
    setDragTarget(target);
  }, []);
  const handleDrop = useCallback((target: SubPane) => {
    const source = dragPane.current;
    if (source && source !== target) {
      const newOrder = [...paneOrder];
      const from = newOrder.indexOf(source);
      const to = newOrder.indexOf(target);
      if (from >= 0 && to >= 0) {
        newOrder.splice(from, 1);
        newOrder.splice(to, 0, source);
        setPaneOrder(newOrder);
      }
    }
    dragPane.current = null;
    setDragTarget(null);
  }, [paneOrder, setPaneOrder]);
  const handleDragEnd = useCallback(() => {
    dragPane.current = null;
    setDragTarget(null);
  }, []);
  const movePane = useCallback((pane: SubPane, direction: -1 | 1) => {
    const current = paneOrder.indexOf(pane);
    const target = current + direction;
    if (current < 0 || target < 0 || target >= paneOrder.length) return;
    const next = [...paneOrder];
    [next[current], next[target]] = [next[target], next[current]];
    setPaneOrder(next);
  }, [paneOrder, setPaneOrder]);
  const openIndicatorSettings = useCallback((key: string | null = null) => {
    setSettingsTarget(key);
    setSettingsOpen(true);
  }, []);

  const paneVisible = Object.fromEntries(paneOrder.map((pane) => {
    const setting = indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane];
    return [pane, (setting?.visible ?? true) && isVisibleForInterval(pane, interval as Interval, setting)];
  })) as Record<SubPane, boolean>;
  const visiblePanes = paneOrder.filter((pane) => paneVisible[pane] && vwapData);
  const subPaneSize = Math.max(8, Math.min(18, Math.floor(40 / Math.max(1, visiblePanes.length))));
  const mainChartSize = 100 - subPaneSize * visiblePanes.length;
  const coverageDays = candleQuality.coverageMs / 86_400_000;
  const hasCandleIssue = candleQuality.rejected > 0 || candleQuality.gaps > 0;

  const mainChart = chartApi;
  const latestDisplayCandle = candleSeriesData.at(-1);
  const displayCandle = hoveredCandle ?? (latestDisplayCandle ? {
    open: Number(latestDisplayCandle.open), high: Number(latestDisplayCandle.high),
    low: Number(latestDisplayCandle.low), close: Number(latestDisplayCandle.close),
  } : null);
  const candlePositive = displayCandle ? displayCandle.close >= displayCandle.open : true;
  const candleChange = displayCandle ? displayCandle.close - displayCandle.open : 0;
  const candleChangePercent = displayCandle?.open ? (candleChange / displayCandle.open) * 100 : 0;
  const resetChartView = useCallback(() => {
    const count = klinesData?.candles.length ?? 0;
    if (!count) return;
    chartRef.current?.timeScale().setVisibleLogicalRange({
      from: Math.max(0, count - preferredVisibleBars(interval) - 1),
      to: count + 9,
    });
    chartRef.current?.priceScale('right').applyOptions({ autoScale: true });
  }, [interval, klinesData?.candles.length]);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement === chartRootRef.current) {
        await document.exitFullscreen();
      } else if (chartRootRef.current) {
        await chartRootRef.current.requestFullscreen();
      }
    } catch {
      // Fullscreen can be denied by browser policy; keep the rest of the chart responsive.
    }
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (event.key === '0') {
        event.preventDefault();
        resetChartView();
      } else if (event.key === 'End') {
        event.preventDefault();
        chartRef.current?.timeScale().scrollToRealTime();
      } else if (event.shiftKey && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        void toggleFullscreen();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [resetChartView, toggleFullscreen]);

  return (
    <div ref={chartRootRef} className="flex flex-col h-full w-full bg-[#07080b] text-[#d1d4dc] overflow-hidden">
      {/* Interval toolbar */}
      <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#252832] bg-[#101116] shrink-0 shadow-[0_1px_0_rgba(255,255,255,0.02)]">
        {/* Sidebar toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title="Toggle indicator panel"
          className={`p-1 rounded transition-colors ${sidebarOpen ? 'text-[#2962ff]' : 'text-[#666] hover:text-[#aaa]'}`}
        >
          <PanelLeft size={16} />
        </button>

        <div className="min-w-0 flex-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <ToggleGroup className="w-max" type="single" value={interval} onValueChange={v => v && setInterval(v as Interval)} size="sm">
            {(Object.keys(INTERVAL_LABELS) as Interval[]).map(i => (
              <ToggleGroupItem
                key={i} value={i}
                disabled={marketType === 'futures' && i.endsWith('s')}
                title={marketType === 'futures' && i.endsWith('s') ? 'Binance USD-M Futures starts at 1-minute candles' : INTERVAL_LABELS[i]}
                className="h-6 px-2 text-[11px] data-[state=on]:bg-[#2962ff] data-[state=on]:text-white text-[#A3A6AF] hover:text-white hover:bg-[#1a1a1a] rounded transition-colors disabled:cursor-not-allowed disabled:opacity-25"
              >
                {INTERVAL_LABELS[i]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-transparent px-2 text-[10px] text-[#aeb4c0] outline-none transition-colors hover:border-[#303542] hover:bg-[#1b1e26] hover:text-white data-[state=open]:border-[#3a4354] data-[state=open]:bg-[#20242e]"
              title="نوع الشموع"
              data-testid="candle-style-menu"
            >
              <CandleStyleGlyph style={candleStyle} />
              <span className="hidden xl:inline">{CANDLE_STYLE_LABELS[candleStyle].en}</span>
              <ChevronDown size={11} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64 border-[#303746] bg-[#11151d] p-1.5 text-[#d7dce7] shadow-2xl">
            <DropdownMenuLabel className="px-2 py-2 text-[11px] font-semibold text-[#8f99aa]">
              نوع الشارت
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-[#252b37]" />
            <DropdownMenuRadioGroup value={candleStyle} onValueChange={(value) => setCandleStyle(value as CandleStyle)}>
              {(Object.keys(CANDLE_STYLE_LABELS) as CandleStyle[]).map((style) => (
                <DropdownMenuRadioItem
                  key={style}
                  value={style}
                  className="cursor-pointer rounded-md py-2 pl-8 pr-2 text-xs focus:bg-[#202a3a] focus:text-white"
                >
                  <span className="flex items-center gap-2">
                    <CandleStyleGlyph style={style} />
                    <span>
                      <span className="block font-medium">{CANDLE_STYLE_LABELS[style].ar}</span>
                      <span className="block text-[9px] text-[#768296]">{CANDLE_STYLE_LABELS[style].en}</span>
                    </span>
                  </span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            {candleStyle === 'heikin-ashi' && (
              <p className="mx-1 mt-1 rounded-md bg-[#182235] px-2 py-1.5 text-[9px] leading-4 text-[#9fb4d8]">
                أسعار هايكين آشي محسوبة ومتوسطة وليست أسعار التنفيذ الفعلية. المؤشرات تبقى مبنية على بيانات المنصة الأصلية.
              </p>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="hidden lg:flex items-center gap-2 text-[10px] tabular-nums">
          {chartQuery.isFetchingNextPage && (
            <span className="flex items-center gap-1 text-[#8f96a3]">
              <LoaderCircle size={12} className="animate-spin text-[#2962ff]" />
              Loading history
            </span>
          )}
          {klinesData?.candles.length ? (
            <span className="hidden sm:flex items-center gap-1 text-[#5e6675]" title="Candles loaded in memory">
              <Database size={11} />
              {klinesData.candles.length.toLocaleString()} bars
            </span>
          ) : null}
          {klinesData?.candles.length ? (
            <span
              title={hasCandleIssue
                ? `${candleQuality.rejected} invalid bars removed; ${candleQuality.gaps} bars still missing`
                : `Validated OHLC data covering ${coverageDays.toFixed(1)} days`}
              className={`hidden md:flex items-center gap-1 ${hasCandleIssue ? 'text-[#f0a13a]' : 'text-[#5fae91]'}`}
            >
              {hasCandleIssue ? <TriangleAlert size={11} /> : <ShieldCheck size={11} />}
              {hasCandleIssue ? `${candleQuality.gaps} gap${candleQuality.gaps === 1 ? '' : 's'}` : `${coverageDays.toFixed(1)}d verified`}
            </span>
          ) : null}
        </div>

        <button
          onClick={() => chartRef.current?.timeScale().scrollToRealTime()}
          title="Go to realtime"
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
        >
          <ChevronsRight size={15} />
        </button>

        <button
          onClick={resetChartView}
          title="Reset chart view (0)"
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
          data-testid="reset-chart-view"
        >
          <RotateCcw size={14} />
        </button>

        <button
          onClick={toggleFullscreen}
          title={`${isFullscreen ? 'Exit' : 'Enter'} fullscreen (Shift+F)`}
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
          data-testid="toggle-chart-fullscreen"
        >
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>

        <button
          onClick={() => openIndicatorSettings(null)}
          title="Indicator settings"
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
        >
          <SlidersHorizontal size={16} />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Indicator sidebar */}
        {sidebarOpen && (
          <IndicatorSidebar
            groups={INDICATOR_GROUPS}
            dynamicKeys={dynamicKeys}
            hoveredValues={hoveredValues}
            expandedGroups={expandedGroups}
            setExpandedGroups={setExpandedGroups}
            onOpenSettings={openIndicatorSettings}
            paneOrder={paneOrder}
            paneVisible={paneVisible}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onDragEnd={handleDragEnd}
          />
        )}

        {/* Charts column */}
        <ResizablePanelGroup direction="vertical" autoSaveId="terminal-sub-pane-layout-v2" className="min-h-0 flex-1 min-w-0 overflow-hidden">
          <ResizablePanel id="main-chart" order={0} defaultSize={mainChartSize} minSize={28} className="min-h-0 overflow-hidden">
          <div className="relative h-full bg-[#07080b]">
            <div ref={chartContainerRef} className="absolute inset-0 cursor-crosshair active:cursor-grabbing" />
            {displayCandle && (
              <div className="pointer-events-none absolute left-3 top-2 z-10 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] drop-shadow-[0_1px_2px_#07080b]">
                <span className="font-sans font-semibold text-[#d1d4dc]">{activeSymbol}</span>
                <span className="text-[#5e6675]">· {INTERVAL_LABELS[interval]}</span>
                <span className="rounded bg-[#181c24]/90 px-1.5 py-0.5 font-sans text-[8px] font-semibold text-[#8792a5]">
                  {CANDLE_STYLE_LABELS[candleStyle].en}
                </span>
                {(['open', 'high', 'low', 'close'] as const).map((key) => (
                  <span key={key} className="text-[#707887]">
                    {key[0].toUpperCase()}{' '}
                    <span className={candlePositive ? 'text-[#089981]' : 'text-[#f23645]'}>
                      {displayCandle[key].toLocaleString(undefined, { maximumFractionDigits: 8 })}
                    </span>
                  </span>
                ))}
                <span className={candlePositive ? 'text-[#089981]' : 'text-[#f23645]'}>
                  {candleChange >= 0 ? '+' : ''}{candleChange.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                  {' '}({candleChangePercent >= 0 ? '+' : ''}{candleChangePercent.toFixed(2)}%)
                </span>
              </div>
            )}
            {chartQuery.isLoading && (
              <div className="absolute inset-0 z-20 grid place-items-center bg-[#07080b]/90 backdrop-blur-sm">
                <div className="flex flex-col items-center gap-3">
                  <LoaderCircle size={28} className="animate-spin text-[#2962ff]" />
                  <div className="text-center">
                    <div className="text-xs font-medium text-[#d1d4dc]">Loading market history</div>
                    <div className="mt-1 text-[10px] text-[#5e6675]">Preparing candles and indicators…</div>
                  </div>
                </div>
              </div>
            )}
            {chartQuery.isError && (
              <div className="absolute inset-0 z-20 grid place-items-center bg-[#07080b]/95">
                <div className="max-w-sm text-center">
                  <div className="text-sm font-semibold text-[#f23645]">Market data unavailable</div>
                  <div className="mt-1 text-[11px] text-[#8f96a3]">{String(chartQuery.error)}</div>
                  <button onClick={() => chartQuery.refetch()} className="mt-3 rounded-md bg-[#2962ff] px-3 py-1.5 text-xs text-white hover:bg-[#1e53dc]">
                    Retry
                  </button>
                </div>
              </div>
            )}
          </div>
          </ResizablePanel>

          {/* Drag a pane by its title. Resize it from the divider above it. */}
          {vwapData && visiblePanes.map((pane, paneIndex) => {
            return (
              <Fragment key={pane}>
                <ResizableHandle withHandle className="z-20 h-[6px] shrink-0 cursor-row-resize touch-none bg-[#1c212b] hover:bg-[#2962ff] data-[resize-handle-active]:bg-[#2962ff] transition-colors" />
                <ResizablePanel
                  id={`indicator-pane-${pane.replaceAll(' ', '-').toLowerCase()}`}
                  order={paneIndex + 1}
                  defaultSize={subPaneSize}
                  minSize={7}
                  maxSize={48}
                  className="min-h-0 overflow-hidden"
                >
                  <DraggablePane
                    label={pane}
                    onDragStart={() => handleDragStart(pane)}
                    onDragOver={e => handleDragOver(e, pane)}
                    onDrop={() => handleDrop(pane)}
                    onDragEnd={handleDragEnd}
                    dropActive={dragTarget === pane}
                    onMoveUp={() => movePane(pane, -1)}
                    onMoveDown={() => movePane(pane, 1)}
                    canMoveUp={paneOrder.indexOf(pane) > 0}
                    canMoveDown={paneOrder.indexOf(pane) < paneOrder.length - 1}
                    onSettings={() => openIndicatorSettings(pane)}
                    onResetScale={() => {
                      const paneChart = paneCrosshairsRef.current.get(pane)?.chart;
                      paneChart?.priceScale('right').applyOptions({ autoScale: true });
                      const range = chartRef.current?.timeScale().getVisibleRange();
                      if (paneChart && range) paneChart.timeScale().setVisibleRange(range);
                    }}
                  >
                    {pane === 'Dollar Volume'  && <DollarVolumeChart paneId={pane} registerCrosshair={registerPaneCrosshair} onCrosshairMove={handlePaneCrosshairMove} data={vwapData.dollarVolume} mainChart={mainChart} setting={indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane]} />}
                    {pane === 'Combined Signal' && <CombinedSignalChart paneId={pane} registerCrosshair={registerPaneCrosshair} onCrosshairMove={handlePaneCrosshairMove} data={vwapData.combinedSignal} mainChart={mainChart} setting={indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane]} />}
                    {pane === 'Integrated Dashboard' && <IntegratedDashboard data={vwapData.integratedDashboard} />}
                    {pane === 'Session Volume' && <SessionVolumeChart paneId={pane} registerCrosshair={registerPaneCrosshair} onCrosshairMove={handlePaneCrosshairMove} data={vwapData.sessionVolumeAccumulated} mainChart={mainChart} setting={indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane]} />}
                    {pane === 'Relative QV'   && <RelativeQvChart paneId={pane} registerCrosshair={registerPaneCrosshair} onCrosshairMove={handlePaneCrosshairMove} data={vwapData.relativeQv} mainChart={mainChart} setting={indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane]} />}
                    {pane === 'ZScore'        && <ZScoreChart paneId={pane} registerCrosshair={registerPaneCrosshair} onCrosshairMove={handlePaneCrosshairMove} data={vwapData.zScore ?? []} mainChart={mainChart} setting={indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane]} settings={indicatorSettings} />}
                  </DraggablePane>
                </ResizablePanel>
              </Fragment>
            );
          })}
        </ResizablePanelGroup>

        {settingsOpen && (
          <Suspense fallback={null}>
            <IndicatorSettingsModal
              open
              indicatorKey={settingsTarget ?? undefined}
              onClose={() => {
                setSettingsOpen(false);
                setSettingsTarget(null);
              }}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}

// ── Indicator Sidebar ─────────────────────────────────────────────────────────

function IndicatorSidebar({
  groups, dynamicKeys, hoveredValues, expandedGroups, setExpandedGroups,
  onOpenSettings, paneOrder, paneVisible, onDragStart, onDragOver, onDrop, onDragEnd,
}: {
  groups: IndicatorGroup[];
  dynamicKeys: { vwma: string[]; mtf: string[] };
  hoveredValues: Record<string, number>;
  expandedGroups: Record<string, boolean>;
  setExpandedGroups: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  onOpenSettings: (key: string) => void;
  paneOrder: SubPane[];
  paneVisible: Record<SubPane, boolean>;
  onDragStart: (p: SubPane) => void;
  onDragOver: (e: React.DragEvent, p: SubPane) => void;
  onDrop: (pane: SubPane) => void;
  onDragEnd: () => void;
}) {
  const { indicatorSettings, toggleIndicator, interval } = useTradingStore();
  const toggleGroup = (label: string) =>
    setExpandedGroups(prev => ({ ...prev, [label]: !prev[label] }));

  return (
    <div className="w-[190px] shrink-0 border-r border-[#1a1a1a] bg-[#080808] flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        {groups.map(group => {
          const isExpanded = expandedGroups[group.label] ?? true;

          // Sub-Panes — draggable
          if (group.label === 'Sub-Panes') {
            return (
              <div key="Sub-Panes" className="border-b border-[#111] pb-1">
                <GroupHeader label="Sub-Panes" isExpanded={isExpanded} onToggle={() => toggleGroup('Sub-Panes')} />
                {isExpanded && paneOrder.map(pane => {
                  const setting = indicatorSettings[pane] ?? DEFAULT_INDICATOR_SETTINGS[pane];
                  const vis = paneVisible[pane];
                  return (
                    <div
                      key={pane} draggable
                      onDragStart={() => onDragStart(pane)}
                      onDragOver={e => onDragOver(e, pane)}
                      onDrop={() => onDrop(pane)}
                      onDragEnd={onDragEnd}
                      className="flex items-center justify-between px-2 py-1 hover:bg-[#111] cursor-grab active:cursor-grabbing"
                    >
                      <div className="flex items-center gap-1.5 overflow-hidden min-w-0">
                        <GripVertical size={10} className="text-[#333] shrink-0" />
                        <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: setting?.color ?? '#fff', opacity: vis ? 1 : 0.3 }} />
                        <span className={`text-[10px] truncate ${vis ? 'text-[#ccc]' : 'text-[#444]'}`}>{pane}</span>
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0 ml-1">
                        <EyeToggle settingKey={pane} visible={vis} onToggle={() => toggleIndicator(pane)} />
                        <button onClick={() => onOpenSettings(pane)} className="text-[#555] hover:text-[#aaa] p-0.5 rounded">
                          <Settings2 size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          }

          // Dynamic groups (VWMA Auto, VWMA MTF)
          if (group.rows.some(r => r.dynamicPrefix)) {
            const keys = group.rows[0].dynamicPrefix === 'VWMA' ? dynamicKeys.vwma : dynamicKeys.mtf;
            return (
              <div key={group.label} className="border-b border-[#111] pb-1">
                <GroupHeader
                  label={group.label}
                  isExpanded={isExpanded}
                  onToggle={() => toggleGroup(group.label)}
                  settingKey={group.settingKey}
                  onSettings={group.settingKey ? () => onOpenSettings(group.settingKey!) : undefined}
                />
                {isExpanded && keys.map(key => {
                  const groupSetting = indicatorSettings[group.settingKey!] ?? DEFAULT_INDICATOR_SETTINGS[group.settingKey!];
                  const tfVisible = isVisibleForInterval(key, interval as Interval, groupSetting);
                  const vis = (groupSetting?.visible ?? true) && tfVisible;
                  return (
                    <IndicatorRow
                      key={key} settingKey={key} label={key}
                      visible={vis}
                      hovered={hoveredValues[key]}
                      isTfHidden={!tfVisible}
                      onToggle={() => toggleIndicator(group.settingKey!)}
                      onSettings={() => onOpenSettings(group.settingKey!)}
                    />
                  );
                })}
                {isExpanded && keys.length === 0 && (
                  <div className="px-3 py-1 text-[9px] text-[#333] italic">Loading…</div>
                )}
              </div>
            );
          }

          // Normal groups
          return (
            <div key={group.label} className="border-b border-[#111] pb-1">
              <GroupHeader
                label={group.label}
                isExpanded={isExpanded}
                onToggle={() => toggleGroup(group.label)}
                settingKey={group.settingKey}
                onSettings={group.settingKey ? () => onOpenSettings(group.settingKey!) : undefined}
              />
              {isExpanded && group.rows.map(row => {
                const setting  = indicatorSettings[row.key] ?? DEFAULT_INDICATOR_SETTINGS[row.key];
                const masterSetting = group.settingKey
                  ? indicatorSettings[group.settingKey] ?? DEFAULT_INDICATOR_SETTINGS[group.settingKey]
                  : undefined;
                const masterVisible = !masterSetting
                  || ((masterSetting.visible ?? true) && isVisibleForInterval(group.settingKey!, interval as Interval, masterSetting));
                const tfHidden = !isVisibleForInterval(row.key, interval as Interval, setting);
                const vis      = masterVisible && (setting?.visible ?? true) && !tfHidden;
                return (
                  <IndicatorRow
                    key={row.key} settingKey={row.key}
                    label={row.label ?? row.key}
                    visible={vis}
                    hovered={hoveredValues[row.key]}
                    isTfHidden={tfHidden}
                    isBand={row.isBand}
                    onToggle={() => toggleIndicator(row.key)}
                    onSettings={() => onOpenSettings(row.key)}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Row atom ──────────────────────────────────────────────────────────────────

function IndicatorRow({
  settingKey, label, visible, hovered, isTfHidden, isBand, onToggle, onSettings,
}: {
  settingKey: string; label: string; visible: boolean; hovered?: number;
  isTfHidden?: boolean; isBand?: boolean; onToggle: () => void; onSettings: () => void;
}) {
  const { indicatorSettings } = useTradingStore();
  const setting = indicatorSettings[settingKey] ?? DEFAULT_INDICATOR_SETTINGS[settingKey];
  const color   = setting?.color ?? '#888';

  return (
    <div
      className="flex items-center justify-between px-2.5 py-[3px] hover:bg-[#0f0f0f] cursor-pointer"
      onClick={onSettings}
    >
      <div className="flex items-center gap-1.5 overflow-hidden min-w-0">
        {isBand ? (
          <div className="w-4 h-[2px] shrink-0 rounded" style={{ backgroundColor: color, opacity: visible ? 0.8 : 0.2, borderTop: `1px dashed ${color}` }} />
        ) : (
          <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color, opacity: visible ? 1 : 0.25 }} />
        )}
        <div className="flex flex-col min-w-0 leading-none">
          <span className={`text-[10px] truncate ${visible ? 'text-[#ccc]' : 'text-[#444]'}`}>{label}</span>
          {hovered !== undefined && (
            <span className="text-[9px] text-[#666] tabular-nums">{hovered.toFixed(2)}</span>
          )}
          {isTfHidden && (
            <span className="text-[8px] text-[#333]">hidden TF</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-0.5 shrink-0 ml-1" onClick={e => e.stopPropagation()}>
        <EyeToggle settingKey={settingKey} visible={visible} onToggle={onToggle} />
        <button onClick={onSettings} className="text-[#555] hover:text-[#aaa] p-0.5 rounded">
          <Settings2 size={11} />
        </button>
      </div>
    </div>
  );
}

// Always-visible eye toggle button
function EyeToggle({ settingKey: _key, visible, onToggle }: { settingKey: string; visible: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={e => { e.stopPropagation(); onToggle(); }}
      className={`p-0.5 rounded transition-colors ${visible ? 'text-[#888] hover:text-white' : 'text-[#333] hover:text-[#888]'}`}
    >
      {visible ? <Eye size={11} /> : <EyeOff size={11} />}
    </button>
  );
}

function GroupHeader({ label, isExpanded, onToggle, settingKey, onSettings }: {
  label: string; isExpanded: boolean; onToggle: () => void; settingKey?: string; onSettings?: () => void;
}) {
  const { indicatorSettings, toggleIndicator } = useTradingStore();
  const setting = settingKey
    ? indicatorSettings[settingKey] ?? DEFAULT_INDICATOR_SETTINGS[settingKey]
    : undefined;
  return (
    <div className="flex items-center justify-between px-2.5 py-1.5 hover:bg-[#0f0f0f] select-none group/gh">
      <div className="flex items-center gap-1.5 cursor-pointer" onClick={onToggle}>
        {isExpanded ? <ChevronDown size={11} className="text-[#444]" /> : <ChevronRight size={11} className="text-[#444]" />}
        <span className="text-[10px] font-semibold text-[#666] tracking-wide uppercase">{label}</span>
      </div>
      {settingKey && (
        <div className="flex items-center gap-0.5">
          <EyeToggle settingKey={settingKey} visible={setting?.visible !== false} onToggle={() => toggleIndicator(settingKey)} />
          {onSettings && (
            <button onClick={onSettings} className="rounded p-0.5 text-[#555] hover:text-[#aaa]" title={`Settings: ${label}`}>
              <Settings2 size={11} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Draggable Sub-Pane wrapper ────────────────────────────────────────────────

function DraggablePane({
  label, children, onDragStart, onDragOver, onDrop, onDragEnd, dropActive,
  onMoveUp, onMoveDown, canMoveUp, canMoveDown, onSettings, onResetScale,
}: {
  label: string; children: React.ReactNode;
  onDragStart: () => void; onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void; onDragEnd: () => void; dropActive: boolean;
  onMoveUp: () => void; onMoveDown: () => void;
  canMoveUp: boolean; canMoveDown: boolean; onSettings: () => void; onResetScale: () => void;
}) {
  return (
    <div
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={`h-full min-h-0 overflow-hidden flex flex-col relative bg-[#07080b] group/pane transition-shadow ${
        dropActive ? 'ring-1 ring-inset ring-[#2962ff] shadow-[inset_0_18px_30px_rgba(41,98,255,0.08)]' : ''
      }`}
    >
      <div className="absolute left-2 top-1 z-10 flex items-center overflow-hidden rounded-md border border-[#202633]/80 bg-[#0b0f17]/90 shadow-sm backdrop-blur">
        <button
          draggable
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          className="flex min-w-0 cursor-grab items-center gap-1 px-1.5 py-1 active:cursor-grabbing hover:bg-[#151821]"
          title="Drag to reorder this pane"
        >
          <GripVertical size={11} className="shrink-0 text-[#566078]" />
          <span className="max-w-40 truncate text-[9px] font-bold uppercase tracking-wider text-[#8390a5]">{label}</span>
        </button>
        <div className="h-4 w-px bg-[#252d3b]" />
        <button onClick={onMoveUp} disabled={!canMoveUp} className="p-1 text-[#69758b] hover:bg-[#182033] hover:text-white disabled:cursor-not-allowed disabled:opacity-25" title="Move pane up">
          <ArrowUp size={11} />
        </button>
        <button onClick={onMoveDown} disabled={!canMoveDown} className="p-1 text-[#69758b] hover:bg-[#182033] hover:text-white disabled:cursor-not-allowed disabled:opacity-25" title="Move pane down">
          <ArrowDown size={11} />
        </button>
        <button onClick={onSettings} className="p-1 text-[#69758b] hover:bg-[#182033] hover:text-white" title="Open this indicator settings">
          <Settings2 size={11} />
        </button>
        <button onClick={onResetScale} className="p-1 text-[#69758b] hover:bg-[#182033] hover:text-white" title="Center indicator and reset its value scale">
          <RotateCcw size={11} />
        </button>
      </div>
      {children}
    </div>
  );
}

// ── Sub-chart time-sync ───────────────────────────────────────────────────────

function syncTimeScale(child: IChartApi, parent: IChartApi | null): () => void {
  if (!parent) return () => {};
  const parentScale = parent.timeScale();
  const childScale = child.timeScale();
  let syncingFromParent = false;
  let syncingFromChild = false;
  const sameRange = (left: { from: Time; to: Time } | null, right: { from: Time; to: Time } | null) =>
    left === right || Boolean(left && right && Number(left.from) === Number(right.from) && Number(left.to) === Number(right.to));
  const syncFromParent = (range: { from: Time; to: Time } | null) => {
    if (!range || syncingFromChild || sameRange(range, childScale.getVisibleRange())) return;
    syncingFromParent = true;
    try {
      childScale.setVisibleRange(range);
    } catch {
      // A chart can be disposed while a resize or range event is still queued.
    } finally {
      syncingFromParent = false;
    }
  };
  const syncFromChild = (range: { from: Time; to: Time } | null) => {
    if (!range || syncingFromParent || sameRange(range, parentScale.getVisibleRange())) return;
    syncingFromChild = true;
    try {
      parentScale.setVisibleRange(range);
    } catch {
      // Keep the remaining charts interactive if one pane disappears mid-drag.
    } finally {
      syncingFromChild = false;
    }
  };
  parentScale.subscribeVisibleTimeRangeChange(syncFromParent);
  childScale.subscribeVisibleTimeRangeChange(syncFromChild);
  syncFromParent(parentScale.getVisibleRange());
  return () => {
    try { parentScale.unsubscribeVisibleTimeRangeChange(syncFromParent); } catch {}
    try { childScale.unsubscribeVisibleTimeRangeChange(syncFromChild); } catch {}
  };
}

interface SubChartBuildResult {
  series: ISeriesApi<any>;
  valueAtTime: (time: number) => number | null;
}

interface SyncedSubChartProps {
  paneId: string;
  mainChart: IChartApi | null;
  setting: IndicatorSetting;
  registerCrosshair: RegisterPaneCrosshair;
  onCrosshairMove: PaneCrosshairMove;
}

function useSubChart(
  containerRef: React.RefObject<HTMLDivElement | null>,
  mainChart: IChartApi | null,
  paneId: string,
  registerCrosshair: RegisterPaneCrosshair,
  onCrosshairMove: PaneCrosshairMove,
  build: (chart: IChartApi) => SubChartBuildResult | undefined,
  deps: any[],
) {
  useEffect(() => {
    if (!containerRef.current) return;
    const chart      = subChartBase(containerRef.current as HTMLDivElement);
    const unsubSync  = syncTimeScale(chart, mainChart);
    const registration = build(chart);
    if (registration) registerCrosshair(paneId, { chart, ...registration });
    const handleCrosshair = (param: { time?: Time }) => onCrosshairMove(paneId, param.time ?? null);
    const resetValueScale = () => chart.priceScale('right').applyOptions({ autoScale: true });
    chart.subscribeCrosshairMove(handleCrosshair);
    chart.subscribeDblClick(resetValueScale);
    return () => {
      try { chart.unsubscribeCrosshairMove(handleCrosshair); } catch {}
      try { chart.unsubscribeDblClick(resetValueScale); } catch {}
      registerCrosshair(paneId, null);
      unsubSync();
      try { chart.remove(); } catch {}
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

// ── Sub-chart components ──────────────────────────────────────────────────────

function applyPanePreferences(series: ISeriesApi<any>, setting: IndicatorSetting) {
  series.applyOptions({
    lastValueVisible: setting.showLastValue ?? true,
    priceLineVisible: setting.showPriceLine ?? false,
  });
}

function paneColor(setting: IndicatorSetting): string {
  return colorWithOpacity(setting.color, (setting.opacity ?? 100) / 100);
}

function DollarVolumeChart({ data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove }: SyncedSubChartProps & { data: any }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, paneId, registerCrosshair, onCrosshairMove, (chart) => {
    const color = paneColor(setting);
    const useDataColors = setting.color === DEFAULT_INDICATOR_SETTINGS['Dollar Volume'].color && (setting.opacity ?? 100) === 100;
    const hist = chart.addSeries(HistogramSeries, { color, priceLineVisible: setting.showPriceLine ?? false, lastValueVisible: setting.showLastValue ?? true });
    hist.setData(data.perCandle.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color: useDataColors ? (v.color ?? color) : color,
    })));
    const sma = makeLine(chart, color, setting.lineWidth, setting.lineStyle); applyPanePreferences(sma, setting); setLineData(sma, data.sma30.values);
    const t1  = makeLine(chart, '#ffffff', 3, 0); setLineData(t1, data.minimumThreshold.values);
    const t2  = makeLine(chart, '#0000ff', 3, 0); setLineData(t2, data.optimalThreshold.values);
    return { series: hist, valueAtTime: valueLookup(data.perCandle.values) };
  }, [data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove]);
  return <div ref={ref} className="min-h-0 flex-1 pt-6" />;
}

function CombinedSignalChart({ data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove }: SyncedSubChartProps & { data: any }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, paneId, registerCrosshair, onCrosshairMove, (chart) => {
    if (!data?.values?.length) return;
    const signal = makeLine(chart, paneColor(setting), setting.lineWidth, setting.lineStyle, true, LineType.WithSteps); applyPanePreferences(signal, setting);
    setLineData(signal, data.values);
    const zero = makeLine(chart, '#555555', 1, 2, true);
    const first = data.values[0].time;
    const last = data.values[data.values.length - 1].time;
    zero.setData([
      { time: (first / 1000) as Time, value: 0 },
      { time: (last / 1000) as Time, value: 0 },
    ]);
    return { series: signal, valueAtTime: valueLookup(data.values) };
  }, [data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove]);
  return <div ref={ref} className="min-h-0 flex-1 pt-6" />;
}

function compactDashboardNumber(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '∅';
  const absolute = Math.abs(value);
  if (absolute >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (absolute >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (absolute >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toFixed(2);
}

function dashboardMetricColor(kind: 'session' | 'dollar' | 'rqvol' | 'zscore', value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '#555';
  if (kind === 'session') return value < 8e6 ? '#f23645' : value < 50e6 ? '#ff9800' : '#0ecb81';
  if (kind === 'dollar') return value < 1e5 ? '#f23645' : value < 1e6 ? '#ff9800' : '#0ecb81';
  if (kind === 'rqvol') return value < 2 ? '#f23645' : value < 3 ? '#bf8654' : value < 5 ? '#ff9800' : '#0ecb81';
  return value < -0.875 ? '#f23645' : value < 0 ? '#ff9800' : value < 0.875 ? '#2962ff' : '#0ecb81';
}

function IntegratedDashboard({ data }: { data: any }) {
  const rows = data?.rows ?? [];
  const headers = ['FRAME', 'Session_Vol', 'Dv', 'Dv_MA', 'R/QVOL', 'Vwap_Z1', 'Vwap_Z2', 'Signal'];
  return (
    <div className="flex-1 overflow-auto px-2 pb-1 pt-5 font-mono text-[9px]">
      <table className="w-full min-w-[650px] border-collapse text-right">
        <thead><tr>{headers.map(header => <th key={header} className="sticky top-0 bg-[#555] px-2 py-1 text-white">{header}</th>)}</tr></thead>
        <tbody>{rows.map((row: any) => {
          const signalText = row.signal === 1 ? 'BUY' : row.signal === -1 ? 'SELL' : row.signal === null ? '∅' : 'NONE';
          const signalColor = row.signal === 1 ? '#0ecb81' : row.signal === -1 ? '#f23645' : '#ff9800';
          return <tr key={row.interval} className="border-t border-[#1d2028] bg-black">
            <td className="px-2 py-0.5 font-bold text-white">{row.frame}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('session', row.sessionVolume) }}>{compactDashboardNumber(row.sessionVolume)}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('dollar', row.dollarVolume) }}>{compactDashboardNumber(row.dollarVolume)}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('dollar', row.dollarVolumeSma) }}>{compactDashboardNumber(row.dollarVolumeSma)}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('rqvol', row.relativeQv) }}>{compactDashboardNumber(row.relativeQv)}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('zscore', row.zVwap1) }}>{compactDashboardNumber(row.zVwap1)}</td>
            <td className="px-2 py-0.5" style={{ color: dashboardMetricColor('zscore', row.zVwap2) }}>{compactDashboardNumber(row.zVwap2)}</td>
            <td className="px-2 py-0.5 font-bold" style={{ color: signalColor }}>{signalText}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}

function SessionVolumeChart({ data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove }: SyncedSubChartProps & { data: any }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, paneId, registerCrosshair, onCrosshairMove, (chart) => {
    const color = paneColor(setting);
    const hist = chart.addSeries(HistogramSeries, { color, priceLineVisible: setting.showPriceLine ?? false, lastValueVisible: setting.showLastValue ?? true });
    hist.setData(data.accumulated.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color,
    })));
    const t1 = makeLine(chart, '#ffffff', 3, 0); setLineData(t1, data.minimumThreshold.values);
    const t2 = makeLine(chart, '#0000ff', 3, 0); setLineData(t2, data.optimalThreshold.values);
    return { series: hist, valueAtTime: valueLookup(data.accumulated.values) };
  }, [data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove]);
  return <div ref={ref} className="min-h-0 flex-1 pt-6" />;
}

function RelativeQvChart({ data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove }: SyncedSubChartProps & { data: any }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, paneId, registerCrosshair, onCrosshairMove, (chart) => {
    const line = makeLine(chart, paneColor(setting), setting.lineWidth, setting.lineStyle); applyPanePreferences(line, setting); setLineData(line, data.relative.values);
    const t1   = makeLine(chart, '#ffffff', 2, 0); setLineData(t1, data.minimumThreshold.values);
    return { series: line, valueAtTime: valueLookup(data.relative.values) };
  }, [data, mainChart, setting, paneId, registerCrosshair, onCrosshairMove]);
  return <div ref={ref} className="min-h-0 flex-1 pt-6" />;
}

const ZSCORE_LEVELS = [-2, -1, 0, 1, 2] as const;

function ZScoreChart({
  data, mainChart, paneId, registerCrosshair, onCrosshairMove, settings,
}: SyncedSubChartProps & { data: any[]; settings: IndicatorSettings }) {
  const ref = useRef<HTMLDivElement>(null);
  const { interval } = useTradingStore();
  useSubChart(ref, mainChart, paneId, registerCrosshair, onCrosshairMove, (chart) => {
    let primarySeries: ISeriesApi<any> | null = null;
    let primaryValues: Array<{ time: number; value: number | null }> = [];
    let primaryLookup: ((time: number) => number | null) | null = null;
    data.forEach((line, index) => {
      const key = line.name || `ZScore ${index === 0 ? 48 : 84}`;
      const lineSetting = settings[key] ?? DEFAULT_INDICATOR_SETTINGS[key] ?? DEFAULT_INDICATOR_SETTINGS.ZScore;
      if (!lineSetting.visible || !isVisibleForInterval(key, interval as Interval, lineSetting)) return;
      const series = createSeriesForPlotType(
        chart,
        lineSetting.plotType ?? 'line',
        paneColor(lineSetting),
        lineSetting.lineWidth,
        lineSetting.lineStyle,
        true,
      );
      applyPanePreferences(series, lineSetting);
      series.applyOptions({ priceFormat: { type: 'price', precision: 3, minMove: 0.001 } });
      setLineData(series, line.values, false);
      if (!primarySeries && line.values?.length) {
        primarySeries = series;
        primaryValues = line.values;
        primaryLookup = valueLookup(line.values);
      }
    });

    // Every reference level is an independent plot with its own persisted style.
    if (data[0]?.values?.length) {
      const pts = data[0].values;
      const start = (pts[0].time / 1000) as Time;
      const end   = (pts[pts.length - 1].time / 1000) as Time;
      ZSCORE_LEVELS.forEach(level => {
        const key = `ZScore Level ${level}`;
        const levelSetting = settings[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
        if (!levelSetting?.visible || !isVisibleForInterval(key, interval as Interval, levelSetting)) return;
        const levelLine = makeLine(
          chart,
          paneColor(levelSetting),
          levelSetting.lineWidth,
          levelSetting.lineStyle,
          true,
        );
        applyPanePreferences(levelLine, levelSetting);
        levelLine.applyOptions({ priceFormat: { type: 'price', precision: 3, minMove: 0.001 } });
        levelLine.setData([
          { time: start, value: level },
          { time: end,   value: level },
        ]);
        if (!primarySeries) {
          primarySeries = levelLine;
          primaryValues = [];
          primaryLookup = () => level;
        }
      });
    }
    return primarySeries
      ? { series: primarySeries, valueAtTime: primaryLookup ?? valueLookup(primaryValues) }
      : undefined;
  }, [data, mainChart, interval, settings, paneId, registerCrosshair, onCrosshairMove]);
  return <div ref={ref} className="min-h-0 flex-1 pt-6" />;
}
