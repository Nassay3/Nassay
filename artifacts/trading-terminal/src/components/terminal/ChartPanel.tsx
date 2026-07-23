import { useEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from 'react';
import {
  createChart, ColorType, IChartApi, ISeriesApi,
  Time, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries, LineType, CrosshairMode,
} from 'lightweight-charts';
import {
  useTradingStore, Interval, INTERVAL_LABELS, DEFAULT_INDICATOR_SETTINGS,
  isVisibleForInterval, SubPane,
} from '@/context/TradingContext';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { wsManager } from '@/lib/ws';
import { useChartData, mergeChartPages } from '@/lib/chartData';
import { Eye, EyeOff, Settings2, ChevronDown, ChevronRight, GripVertical, PanelLeft, SlidersHorizontal, LoaderCircle, Database, ChevronsRight, Maximize2 } from 'lucide-react';

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
    bottomColor: `${color}20`,
    lineWidth,
    lineStyle,
    visible,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    priceLineVisible: false,
  });
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
    timeScale: { visible: false },
    rightPriceScale: { borderColor: '#252832', scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 72 },
    crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#758096', style: 3 }, horzLine: { color: '#758096', style: 3 } },
    handleScroll: false,
    handleScale: false,
  });
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
    label: 'Sessions', rows: [
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
      { key: 'Combined Signal' }, { key: 'BEFORE ITS TOO LATE' }, { key: 'Integrated Dashboard' }, { key: 'Dollar Volume' }, { key: 'Session Volume' },
      { key: 'Relative QV' },  { key: 'ZScore' },
    ],
  },
];

// ── Main component ────────────────────────────────────────────────────────────

export default function ChartPanel() {
  const {
    activeSymbol, interval, setInterval,
    indicatorSettings, toggleIndicator,
    paneOrder, setPaneOrder,
    sidebarOpen, setSidebarOpen,
  } = useTradingStore();

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const [chartApi, setChartApi] = useState<IChartApi | null>(null);

  const seriesRefs = useRef({
    candle:    null as ISeriesApi<'Candlestick'> | null,
    volume:    null as ISeriesApi<'Histogram'>   | null,
    lines:     new Map<string, ISeriesApi<any>>(),   // key → main line (Line/Area/Histogram)
    bandLines: new Map<string, ISeriesApi<any>[]>(), // bandKey → [upper,lower] × nBands
  });
  const seriesNameMap = useRef(new Map<ISeriesApi<any>, string>());

  const [hoveredValues, setHoveredValues]   = useState<Record<string, number>>({});
  const [hoveredCandle, setHoveredCandle]   = useState<{ open: number; high: number; low: number; close: number } | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [settingsOpen, setSettingsOpen]   = useState(false);
  const [dynamicKeys, setDynamicKeys]       = useState<{ vwma: string[]; mtf: string[] }>({ vwma: [], mtf: [] });
  const dragPane = useRef<SubPane | null>(null);
  const fittedDataKey = useRef<string | null>(null);
  const crosshairFrame = useRef<number | null>(null);
  const pendingHoveredValues = useRef<Record<string, number>>({});
  const pendingHoveredCandle = useRef<{ open: number; high: number; low: number; close: number } | null>(null);

  const chartQuery = useChartData(activeSymbol, interval);
  const mergedData = useMemo(
    () => chartQuery.data ? mergeChartPages(chartQuery.data.pages) : null,
    [chartQuery.data],
  );
  const klinesData = useMemo(
    () => mergedData ? { candles: mergedData.candles } : null,
    [mergedData],
  );
  const vwapData = mergedData?.indicators;

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
      rightPriceScale: { borderColor: '#252832', scaleMargins: { top: 0.08, bottom: 0.16 }, minimumWidth: 72 },
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
      borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645',
      priceLineColor: '#2962ff',
    });
    seriesRefs.current.volume = chart.addSeries(HistogramSeries, {
      color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        pendingHoveredCandle.current = null;
        return;
      }
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
      seriesRefs.current.volume = null;
      seriesRefs.current.lines.clear();
      seriesRefs.current.bandLines.clear();
      seriesNameMap.current.clear();
    };
  }, []);

  useEffect(() => {
    chartRef.current?.timeScale().applyOptions({
      timeVisible: true,
      secondsVisible: interval.endsWith('s'),
    });
  }, [interval]);

  // ── Load candles ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!klinesData || !seriesRefs.current.candle) return;
    const dataKey = `${activeSymbol}:${interval}`;
    const preservedRange = fittedDataKey.current === dataKey
      ? chartRef.current?.timeScale().getVisibleRange()
      : null;
    seriesRefs.current.candle.setData(
      klinesData.candles.map(k => ({
        time: (k.openTime / 1000) as Time,
        open: parseFloat(k.open), high: parseFloat(k.high),
        low:  parseFloat(k.low),  close: parseFloat(k.close),
      })),
    );
    seriesRefs.current.volume?.setData(
      klinesData.candles.map(k => ({
        time: (k.openTime / 1000) as Time, value: parseFloat(k.volume),
        color: parseFloat(k.close) >= parseFloat(k.open) ? 'rgba(8,153,129,0.35)' : 'rgba(242,54,69,0.35)',
      })),
    );
    if (fittedDataKey.current !== dataKey && klinesData.candles.length) {
      const last = klinesData.candles.length - 1;
      chartRef.current?.timeScale().setVisibleLogicalRange({
        from: Math.max(0, last - 180),
        to: last + 10,
      });
      fittedDataKey.current = dataKey;
    } else if (preservedRange) {
      chartRef.current?.timeScale().setVisibleRange(preservedRange);
    }
  }, [klinesData, activeSymbol, interval]);

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
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
  }, [chartQuery.fetchNextPage, chartQuery.hasNextPage, chartQuery.isFetchingNextPage, activeSymbol, interval]);

  // ── Load VWAP indicators ───────────────────────────────────────────────────
  useEffect(() => {
    if (!chartRef.current || !vwapData) return;
    const chart = chartRef.current;
    const { lines, bandLines } = seriesRefs.current;

    /** Upsert a single series and fill its data based on plot type */
    const syncLine = (
      key: string,
      data: { color: string; values: { time: number; value: number | null; color?: string }[] } | null | undefined,
      overrides?: { lineWidth?: 1|2|3; lineStyle?: 0|1|2|3 },
    ) => {
      if (!data?.values) return;
      const dynamicGroup = key.startsWith('VWMA ')
        ? (key.includes('[') ? 'VWMA MTF' : 'VWMA Auto')
        : null;
      const settingKey = dynamicGroup ?? key;
      const setting    = indicatorSettings[settingKey] ?? DEFAULT_INDICATOR_SETTINGS[settingKey];
      const tfVisible  = isVisibleForInterval(key, interval as Interval);
      const visible    = (setting?.visible ?? true) && tfVisible;
      const plotType   = setting?.plotType ?? 'line';
      const color      = dynamicGroup ? data.color : (setting?.color ?? data.color);
      const lineWidth  = overrides?.lineWidth ?? setting?.lineWidth ?? 1;
      const lineStyle  = overrides?.lineStyle ?? setting?.lineStyle ?? 0;

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
        series = createSeriesForPlotType(chart, plotType, color, lineWidth, lineStyle, visible);
        lines.set(key, series);
        seriesNameMap.current.set(series, key);
      } else {
        const kind = plotTypeSeriesKind(plotType);
        if (kind === 'Histogram') series.applyOptions({ visible, color });
        else if (kind === 'Area') series.applyOptions({
          visible, lineColor: color, topColor: color, bottomColor: `${color}20`, lineWidth, lineStyle,
        });
        else series.applyOptions({
          visible, color, lineWidth,
          lineStyle: plotType.includes('broken') || plotType === 'cross' ? plotTypeLineStyle(plotType) : lineStyle,
          lineType: plotTypeLineType(plotType),
          lineVisible: plotType !== 'circles',
          pointMarkersVisible: plotType === 'circles',
          pointMarkersRadius: lineWidth,
        });
      }
      const defaultColor = DEFAULT_INDICATOR_SETTINGS[settingKey]?.color;
      const preservePointColors = !setting?.color || setting.color === defaultColor;
      setLineData(series, data.values, preservePointColors);
    };

    /** Upsert band lines (upper + lower) for a given bandKey */
    const syncBands = (
      bandKey: string,            // e.g. "Daily VWAP Bands", "Session Asia Bands"
      rawBands: { upper: { time: number; value: number | null }[]; lower: { time: number; value: number | null }[]; upperColor: string; lowerColor: string }[],
      parentKey: string,          // e.g. "Daily VWAP" — for TF visibility
    ) => {
      // Remove old band series for this key
      const old = bandLines.get(bandKey);
      old?.forEach(s => { try { chart.removeSeries(s); } catch {} });
      bandLines.delete(bandKey);

      const defaultSetting = DEFAULT_INDICATOR_SETTINGS[bandKey];
      const setting  = indicatorSettings[bandKey] ?? defaultSetting;
      const tfOk     = isVisibleForInterval(parentKey, interval as Interval);
      const visible  = (setting?.visible ?? false) && tfOk;
      if (!rawBands.length) return;

      const newSeries: ISeriesApi<'Line'>[] = [];
      for (const band of rawBands) {
        const customColor = setting?.color && setting.color !== defaultSetting?.color;
        const uColor = customColor ? setting.color : band.upperColor;
        const lColor = customColor ? setting.color : band.lowerColor;
        const uStyle = setting?.lineStyle ?? 0;
        const width = setting?.lineWidth ?? 1;
        const u = makeLine(chart, uColor, width, uStyle, visible);
        const l = makeLine(chart, lColor, width, uStyle, visible);
        setLineData(u, band.upper);
        setLineData(l, band.lower);
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

    setDynamicKeys({ vwma: vwmaKeys, mtf: mtfKeys });

  }, [vwapData, interval, indicatorSettings]);

  // ── WebSocket live feed ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!seriesRefs.current.candle) return;
    const unsub = wsManager.onMessage((msg) => {
      if (msg.e === 'kline' && msg.s === activeSymbol) {
        const k = msg.k;
        seriesRefs.current.candle?.update({
          time: (k.t / 1000) as Time,
          open: parseFloat(k.o), high: parseFloat(k.h),
          low:  parseFloat(k.l), close: parseFloat(k.c),
        });
        seriesRefs.current.volume?.update({
          time: (k.t / 1000) as Time, value: parseFloat(k.v),
          color: parseFloat(k.c) >= parseFloat(k.o) ? 'rgba(8,153,129,0.35)' : 'rgba(242,54,69,0.35)',
        });
      }
    });
    return () => { unsub(); };
  }, [activeSymbol]);

  // Refresh the latest indicator point without reloading the historical pages.
  useEffect(() => {
    if (!vwapData) return;
    let stopped = false;
    let controller: AbortController | null = null;

    const updateLine = (line: any) => {
      const point = line?.values?.at(-1);
      const series = line?.name ? seriesRefs.current.lines.get(line.name) : null;
      if (series && point?.value != null) {
        series.update({ time: (point.time / 1000) as Time, value: point.value });
      }
    };

    const refresh = async () => {
      if (stopped || document.visibilityState !== 'visible') return;
      controller = new AbortController();
      try {
        const params = new URLSearchParams({ symbol: activeSymbol, interval, limit: '2' });
        const response = await fetch(`/api/market/chart?${params}`, { signal: controller.signal });
        if (!response.ok || stopped) return;
        const payload = await response.json();
        const snapshot = payload.indicators;
        const latestCandle = payload.candles?.at(-1);
        if (latestCandle) {
          seriesRefs.current.candle?.update({
            time: (latestCandle.openTime / 1000) as Time,
            open: parseFloat(latestCandle.open), high: parseFloat(latestCandle.high),
            low: parseFloat(latestCandle.low), close: parseFloat(latestCandle.close),
          });
          seriesRefs.current.volume?.update({
            time: (latestCandle.openTime / 1000) as Time,
            value: parseFloat(latestCandle.volume),
            color: parseFloat(latestCandle.close) >= parseFloat(latestCandle.open)
              ? 'rgba(8,153,129,0.35)' : 'rgba(242,54,69,0.35)',
          });
        }
        snapshot.multiPeriodVwaps?.forEach(updateLine);
        updateLine(snapshot.dailyVwap?.current);
        updateLine(snapshot.dailyVwap?.previous);
        updateLine(snapshot.weeklyVwap?.current);
        updateLine(snapshot.weeklyVwap?.previous);
        snapshot.sessions?.forEach((session: any) => updateLine(session.vwap));
        snapshot.vwapUltra1?.forEach(updateLine);
        snapshot.vwmaMtfMap?.forEach(updateLine);
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
  }, [activeSymbol, interval, vwapData]);

  // ── Drag-to-reorder sub-panes ─────────────────────────────────────────────
  const handleDragStart = useCallback((pane: SubPane) => { dragPane.current = pane; }, []);
  const handleDragOver  = useCallback((e: React.DragEvent, target: SubPane) => {
    e.preventDefault();
    if (!dragPane.current || dragPane.current === target) return;
    const newOrder = [...paneOrder];
    const from = newOrder.indexOf(dragPane.current);
    const to   = newOrder.indexOf(target);
    newOrder.splice(from, 1);
    newOrder.splice(to, 0, dragPane.current);
    setPaneOrder(newOrder);
  }, [paneOrder, setPaneOrder]);

  const paneVisible: Record<SubPane, boolean> = {
    'Combined Signal': indicatorSettings['Combined Signal']?.visible ?? true,
    'BEFORE ITS TOO LATE': indicatorSettings['BEFORE ITS TOO LATE']?.visible ?? true,
    'Integrated Dashboard': indicatorSettings['Integrated Dashboard']?.visible ?? true,
    'Dollar Volume':  indicatorSettings['Dollar Volume']?.visible  ?? true,
    'Session Volume': indicatorSettings['Session Volume']?.visible ?? true,
    'Relative QV':    indicatorSettings['Relative QV']?.visible    ?? true,
    'ZScore':         indicatorSettings['ZScore']?.visible         ?? true,
  };

  const mainChart = chartApi;
  const lastCandle = klinesData?.candles.at(-1);
  const displayCandle = hoveredCandle ?? (lastCandle ? {
    open: Number(lastCandle.open), high: Number(lastCandle.high),
    low: Number(lastCandle.low), close: Number(lastCandle.close),
  } : null);
  const candlePositive = displayCandle ? displayCandle.close >= displayCandle.open : true;
  const resetChartView = () => {
    const count = klinesData?.candles.length ?? 0;
    if (!count) return;
    chartRef.current?.timeScale().setVisibleLogicalRange({
      from: Math.max(0, count - 181),
      to: count + 9,
    });
    chartRef.current?.priceScale('right').applyOptions({ autoScale: true });
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#07080b] text-[#d1d4dc] overflow-hidden">
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

        <ToggleGroup type="single" value={interval} onValueChange={v => v && setInterval(v as Interval)} size="sm">
          {(Object.keys(INTERVAL_LABELS) as Interval[]).map(i => (
            <ToggleGroupItem
              key={i} value={i}
              className="h-6 px-2 text-[11px] data-[state=on]:bg-[#2962ff] data-[state=on]:text-white text-[#A3A6AF] hover:text-white hover:bg-[#1a1a1a] rounded transition-colors"
            >
              {INTERVAL_LABELS[i]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <div className="ml-auto flex items-center gap-2 text-[10px] tabular-nums">
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
          title="Reset chart view"
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
        >
          <Maximize2 size={14} />
        </button>

        <button
          onClick={() => setSettingsOpen(true)}
          title="Indicator settings"
          className="p-1.5 rounded-md text-[#777f8d] hover:text-white hover:bg-[#242731] transition-colors"
        >
          <SlidersHorizontal size={16} />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Indicator sidebar */}
        {sidebarOpen && (
          <IndicatorSidebar
            groups={INDICATOR_GROUPS}
            dynamicKeys={dynamicKeys}
            hoveredValues={hoveredValues}
            expandedGroups={expandedGroups}
            setExpandedGroups={setExpandedGroups}
            onOpenSettings={() => setSettingsOpen(true)}
            paneOrder={paneOrder}
            paneVisible={paneVisible}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={() => { dragPane.current = null; }}
          />
        )}

        {/* Charts column */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="relative flex-1 min-h-[240px] bg-[#07080b]">
            <div ref={chartContainerRef} className="absolute inset-0 cursor-crosshair active:cursor-grabbing" />
            {displayCandle && (
              <div className="pointer-events-none absolute left-3 top-2 z-10 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] drop-shadow-[0_1px_2px_#07080b]">
                <span className="font-sans font-semibold text-[#d1d4dc]">{activeSymbol}</span>
                <span className="text-[#5e6675]">· {INTERVAL_LABELS[interval]}</span>
                {(['open', 'high', 'low', 'close'] as const).map((key) => (
                  <span key={key} className="text-[#707887]">
                    {key[0].toUpperCase()}{' '}
                    <span className={candlePositive ? 'text-[#089981]' : 'text-[#f23645]'}>
                      {displayCandle[key].toLocaleString(undefined, { maximumFractionDigits: 8 })}
                    </span>
                  </span>
                ))}
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

          {/* Draggable sub-panes */}
          {paneOrder.map(pane => {
            if (!paneVisible[pane] || !vwapData) return null;
            return (
              <DraggablePane
                key={pane} label={pane}
                onDragStart={() => handleDragStart(pane)}
                onDragOver={e => handleDragOver(e, pane)}
                onDrop={() => { dragPane.current = null; }}
              >
                {pane === 'Dollar Volume'  && <DollarVolumeChart  data={vwapData.dollarVolume}            mainChart={mainChart} />}
                {pane === 'Combined Signal' && <CombinedSignalChart data={vwapData.combinedSignal}          mainChart={mainChart} />}
                {pane === 'BEFORE ITS TOO LATE' && <BeforeItsTooLateChart data={vwapData.beforeItsTooLate} mainChart={mainChart} />}
                {pane === 'Integrated Dashboard' && <IntegratedDashboard data={vwapData.integratedDashboard} />}
                {pane === 'Session Volume' && <SessionVolumeChart data={vwapData.sessionVolumeAccumulated} mainChart={mainChart} />}
                {pane === 'Relative QV'   && <RelativeQvChart    data={vwapData.relativeQv}               mainChart={mainChart} />}
                {pane === 'ZScore'        && <ZScoreChart        data={vwapData.zScore ?? []}             mainChart={mainChart} />}
              </DraggablePane>
            );
          })}
        </div>

        {settingsOpen && (
          <Suspense fallback={null}>
            <IndicatorSettingsModal open onClose={() => setSettingsOpen(false)} />
          </Suspense>
        )}
      </div>
    </div>
  );
}

// ── Indicator Sidebar ─────────────────────────────────────────────────────────

function IndicatorSidebar({
  groups, dynamicKeys, hoveredValues, expandedGroups, setExpandedGroups,
  onOpenSettings, paneOrder, paneVisible, onDragStart, onDragOver, onDrop,
}: {
  groups: IndicatorGroup[];
  dynamicKeys: { vwma: string[]; mtf: string[] };
  hoveredValues: Record<string, number>;
  expandedGroups: Record<string, boolean>;
  setExpandedGroups: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  onOpenSettings: () => void;
  paneOrder: SubPane[];
  paneVisible: Record<SubPane, boolean>;
  onDragStart: (p: SubPane) => void;
  onDragOver: (e: React.DragEvent, p: SubPane) => void;
  onDrop: () => void;
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
                      onDrop={onDrop}
                      className="flex items-center justify-between px-2 py-1 hover:bg-[#111] cursor-grab active:cursor-grabbing"
                    >
                      <div className="flex items-center gap-1.5 overflow-hidden min-w-0">
                        <GripVertical size={10} className="text-[#333] shrink-0" />
                        <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: setting?.color ?? '#fff', opacity: vis ? 1 : 0.3 }} />
                        <span className={`text-[10px] truncate ${vis ? 'text-[#ccc]' : 'text-[#444]'}`}>{pane}</span>
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0 ml-1">
                        <EyeToggle settingKey={pane} visible={vis} onToggle={() => toggleIndicator(pane)} />
                        <button onClick={onOpenSettings} className="text-[#555] hover:text-[#aaa] p-0.5 rounded">
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
                <GroupHeader label={group.label} isExpanded={isExpanded} onToggle={() => toggleGroup(group.label)} settingKey={group.settingKey} />
                {isExpanded && keys.map(key => {
                  const vis = (indicatorSettings[group.settingKey!]?.visible ?? true) && isVisibleForInterval(key, interval as Interval);
                  return (
                    <IndicatorRow
                      key={key} settingKey={key} label={key}
                      visible={vis}
                      hovered={hoveredValues[key]}
                      isTfHidden={!isVisibleForInterval(key, interval as Interval)}
                      onToggle={() => toggleIndicator(group.settingKey!)}
                      onSettings={onOpenSettings}
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
              <GroupHeader label={group.label} isExpanded={isExpanded} onToggle={() => toggleGroup(group.label)} settingKey={group.settingKey} />
              {isExpanded && group.rows.map(row => {
                const setting  = indicatorSettings[row.key] ?? DEFAULT_INDICATOR_SETTINGS[row.key];
                const tfHidden = !isVisibleForInterval(row.key.replace(' Bands', ''), interval as Interval);
                const vis      = (setting?.visible ?? true) && !tfHidden;
                return (
                  <IndicatorRow
                    key={row.key} settingKey={row.key}
                    label={row.label ?? row.key}
                    visible={vis}
                    hovered={hoveredValues[row.key]}
                    isTfHidden={tfHidden}
                    isBand={row.isBand}
                    onToggle={() => toggleIndicator(row.key)}
                    onSettings={onOpenSettings}
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

function GroupHeader({ label, isExpanded, onToggle, settingKey }: {
  label: string; isExpanded: boolean; onToggle: () => void; settingKey?: string;
}) {
  const { indicatorSettings, toggleIndicator } = useTradingStore();
  const setting = settingKey ? indicatorSettings[settingKey] : undefined;
  return (
    <div className="flex items-center justify-between px-2.5 py-1.5 hover:bg-[#0f0f0f] select-none group/gh">
      <div className="flex items-center gap-1.5 cursor-pointer" onClick={onToggle}>
        {isExpanded ? <ChevronDown size={11} className="text-[#444]" /> : <ChevronRight size={11} className="text-[#444]" />}
        <span className="text-[10px] font-semibold text-[#666] tracking-wide uppercase">{label}</span>
      </div>
      {settingKey && (
        <EyeToggle settingKey={settingKey} visible={setting?.visible !== false} onToggle={() => toggleIndicator(settingKey)} />
      )}
    </div>
  );
}

// ── Draggable Sub-Pane wrapper ────────────────────────────────────────────────

function DraggablePane({ label, children, onDragStart, onDragOver, onDrop }: {
  label: string; children: React.ReactNode;
  onDragStart: () => void; onDragOver: (e: React.DragEvent) => void; onDrop: () => void;
}) {
  return (
    <div draggable onDragStart={onDragStart} onDragOver={onDragOver} onDrop={onDrop}
      className={`${label === 'Integrated Dashboard' ? 'h-40' : 'h-28'} border-t border-[#252832] shrink-0 flex flex-col relative bg-[#07080b] group/pane`}
    >
      <div className="absolute top-1 left-2 z-10 flex items-center gap-1 pointer-events-none">
        <GripVertical size={10} className="text-[#2a2a2a] group-hover/pane:text-[#444]" />
        <span className="text-[9px] text-[#444] font-bold uppercase tracking-wider">{label}</span>
      </div>
      {children}
    </div>
  );
}

// ── Sub-chart time-sync ───────────────────────────────────────────────────────

function syncTimeScale(child: IChartApi, parent: IChartApi | null): () => void {
  if (!parent) return () => {};
  const ts = parent.timeScale();
  const sync = () => {
    try {
      const r = ts.getVisibleRange();
      if (r) child.timeScale().setVisibleRange(r);
    } catch {}
  };
  ts.subscribeVisibleTimeRangeChange(sync);
  sync();
  return () => { try { ts.unsubscribeVisibleTimeRangeChange(sync); } catch {} };
}

function useSubChart(
  containerRef: React.RefObject<HTMLDivElement | null>,
  mainChart: IChartApi | null,
  build: (chart: IChartApi) => void,
  deps: any[],
) {
  useEffect(() => {
    if (!containerRef.current) return;
    const chart      = subChartBase(containerRef.current as HTMLDivElement);
    const unsubSync  = syncTimeScale(chart, mainChart);
    build(chart);
    return () => {
      unsubSync();
      try { chart.remove(); } catch {}
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

// ── Sub-chart components ──────────────────────────────────────────────────────

function DollarVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#0000ff', priceLineVisible: false, lastValueVisible: true });
    hist.setData(data.perCandle.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color: v.color ?? '#0000ff',
    })));
    const sma = makeLine(chart, '#ffff00', 1, 0); setLineData(sma, data.sma30.values);
    const t1  = makeLine(chart, '#ffffff', 3, 0); setLineData(t1, data.minimumThreshold.values);
    const t2  = makeLine(chart, '#0000ff', 3, 0); setLineData(t2, data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function CombinedSignalChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    if (!data?.values?.length) return;
    const signal = makeLine(chart, '#0000ff', 2, 0, true, LineType.WithSteps);
    setLineData(signal, data.values);
    const zero = makeLine(chart, '#555555', 1, 2, true);
    const first = data.values[0].time;
    const last = data.values[data.values.length - 1].time;
    zero.setData([
      { time: (first / 1000) as Time, value: 0 },
      { time: (last / 1000) as Time, value: 0 },
    ]);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
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

function SessionVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#808080', priceLineVisible: false, lastValueVisible: true });
    hist.setData(data.accumulated.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color: '#808080',
    })));
    const t1 = makeLine(chart, '#ffffff', 3, 0); setLineData(t1, data.minimumThreshold.values);
    const t2 = makeLine(chart, '#0000ff', 3, 0); setLineData(t2, data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function RelativeQvChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const line = makeLine(chart, '#2962ff', 1); setLineData(line, data.relative.values);
    const t1   = makeLine(chart, '#ffffff', 2, 0); setLineData(t1, data.minimumThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function BeforeItsTooLateChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    if (!data?.lines?.length) return;

    data.lines.filter((line: any) => line.visible).forEach((line: any) => {
      const series = chart.addSeries(LineSeries, {
        color: line.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        pointMarkersVisible: Boolean(line.pointMarkersVisible),
        pointMarkersRadius: 2,
      });
      setLineData(series, line.values);
    });

    const points = data.lines.find((line: any) => line.values?.length)?.values;
    if (!points?.length) return;
    const start = (points[0].time / 1000) as Time;
    const end = (points[points.length - 1].time / 1000) as Time;
    data.levels.filter((level: any) => level.visible).forEach((level: any) => {
      const series = makeLine(chart, level.color, 2, 0, true);
      series.setData([{ time: start, value: level.value }, { time: end, value: level.value }]);
    });
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

const ZSCORE_LEVELS = [-2, -1, 0, 1, 2] as const;
const ZSCORE_LEVEL_COLORS: Record<number, string> = {
  '-2': '#f6465d',
  '-1': '#f6465d',
  '0':  '#555555',
  '1':  '#0ecb81',
  '2':  '#0ecb81',
};

function ZScoreChart({ data, mainChart }: { data: any[]; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    data.forEach(line => {
      const s = makeLine(chart, line.color, 1, 0, true);
      setLineData(s, line.values);
    });

    // Static ±2 / ±1 / 0 reference levels
    if (data[0]?.values?.length) {
      const pts = data[0].values;
      const start = (pts[0].time / 1000) as Time;
      const end   = (pts[pts.length - 1].time / 1000) as Time;
      ZSCORE_LEVELS.forEach(level => {
        const levelLine = makeLine(chart, ZSCORE_LEVEL_COLORS[level], 1, 2, true);
        levelLine.setData([
          { time: start, value: level },
          { time: end,   value: level },
        ]);
      });
    }
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}
