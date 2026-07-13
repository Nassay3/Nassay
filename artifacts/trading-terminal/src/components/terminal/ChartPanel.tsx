import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart, ColorType, IChartApi, ISeriesApi,
  Time, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries, LineType, CrosshairMode,
} from 'lightweight-charts';
import {
  useTradingStore, Interval, INTERVAL_LABELS, DEFAULT_INDICATOR_SETTINGS,
  isVisibleForInterval, SubPane,
} from '@/context/TradingContext';
import { useGetHistory, useGetVwap, getGetHistoryQueryKey, getGetVwapQueryKey } from '@workspace/api-client-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { wsManager } from '@/lib/ws';
import { Eye, EyeOff, Settings2, ChevronDown, ChevronRight, GripVertical, PanelLeft, SlidersHorizontal } from 'lucide-react';
import IndicatorSettingsModal from './IndicatorSettingsModal';

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

function setLineData(series: ISeriesApi<any>, pts: { time: number; value: number | null }[]) {
  series.setData(
    pts
      .filter(p => p.value !== null && Number.isFinite(p.value))
      .map(p => ({ time: (p.time / 1000) as Time, value: p.value! })),
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
  return makeLine(chart, color, lineWidth, plotTypeLineStyle(plotType), visible, plotTypeLineType(plotType));
}

function subChartBase(container: HTMLDivElement) {
  return createChart(container, {
    layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 10 },
    grid: { vertLines: { color: '#0d0d0d' }, horzLines: { color: '#0d0d0d' } },
    timeScale: { visible: false },
    rightPriceScale: { borderColor: '#1A1A1A', scaleMargins: { top: 0.1, bottom: 0.1 } },
    crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#2B2B36', style: 2 }, horzLine: { color: '#2B2B36', style: 2 } },
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
      { key: 'Dollar Volume' }, { key: 'Session Volume' },
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

  const seriesRefs = useRef({
    candle:    null as ISeriesApi<'Candlestick'> | null,
    volume:    null as ISeriesApi<'Histogram'>   | null,
    lines:     new Map<string, ISeriesApi<any>>(),   // key → main line (Line/Area/Histogram)
    bandLines: new Map<string, ISeriesApi<any>[]>(), // bandKey → [upper,lower] × nBands
  });
  const seriesNameMap = useRef(new Map<ISeriesApi<any>, string>());

  const [hoveredValues, setHoveredValues]   = useState<Record<string, number>>({});
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [settingsOpen, setSettingsOpen]   = useState(false);
  const [dynamicKeys, setDynamicKeys]       = useState<{ vwma: string[]; mtf: string[] }>({ vwma: [], mtf: [] });
  const dragPane = useRef<SubPane | null>(null);

  // Fetch data
  const klinesParams = { symbol: activeSymbol, interval } as any;
  const { data: klinesData } = useGetHistory(
    klinesParams,
    { query: { queryKey: getGetHistoryQueryKey(klinesParams), refetchOnWindowFocus: false, staleTime: 60000 } },
  );
  const vwapParams = { symbol: activeSymbol, interval } as any;
  const { data: vwapData } = useGetVwap(
    vwapParams,
    { query: { queryKey: getGetVwapQueryKey(vwapParams), refetchOnWindowFocus: false, staleTime: 60000 } },
  );

  // ── Init main chart ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 11 },
      grid: { vertLines: { color: '#0d0d0d' }, horzLines: { color: '#0d0d0d' } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#1A1A1A' },
      rightPriceScale: { borderColor: '#1A1A1A', scaleMargins: { top: 0.08, bottom: 0.2 } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#3a3a4a', style: 2, labelBackgroundColor: '#2962ff' },
        horzLine: { color: '#3a3a4a', style: 2, labelBackgroundColor: '#2962ff' },
      },
    });
    chartRef.current = chart;

    seriesRefs.current.candle = chart.addSeries(CandlestickSeries, {
      upColor: '#0ecb81', downColor: '#f6465d',
      borderVisible: false, wickUpColor: '#0ecb81', wickDownColor: '#f6465d',
    });
    seriesRefs.current.volume = chart.addSeries(HistogramSeries, {
      color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) return;
      const nv: Record<string, number> = {};
      seriesNameMap.current.forEach((name, series) => {
        const d = param.seriesData.get(series);
        if (d && 'value' in d) nv[name] = d.value as number;
      });
      setHoveredValues(nv);
    });

    const onResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
      }
    };
    window.addEventListener('resize', onResize);
    onResize();

    return () => {
      window.removeEventListener('resize', onResize);
      chart.remove();
      chartRef.current = null;
      seriesRefs.current.candle = null;
      seriesRefs.current.volume = null;
      seriesRefs.current.lines.clear();
      seriesRefs.current.bandLines.clear();
      seriesNameMap.current.clear();
    };
  }, []);

  // ── Load candles ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!klinesData || !seriesRefs.current.candle) return;
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
        color: parseFloat(k.close) >= parseFloat(k.open) ? 'rgba(14,203,129,0.35)' : 'rgba(246,70,93,0.35)',
      })),
    );
  }, [klinesData]);

  // ── Load VWAP indicators ───────────────────────────────────────────────────
  useEffect(() => {
    if (!chartRef.current || !vwapData) return;
    const chart = chartRef.current;
    const { lines, bandLines } = seriesRefs.current;

    /** Upsert a single series and fill its data based on plot type */
    const syncLine = (
      key: string,
      data: { color: string; values: { time: number; value: number | null }[] } | null | undefined,
      overrides?: { lineWidth?: 1|2|3; lineStyle?: 0|1|2|3 },
    ) => {
      if (!data?.values) return;
      const setting    = indicatorSettings[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
      const tfVisible  = isVisibleForInterval(key, interval as Interval);
      const visible    = (setting?.visible ?? true) && tfVisible;
      const plotType   = setting?.plotType ?? 'line';
      const color      = setting?.color ?? data.color;
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
        series.applyOptions({ visible });
        if (plotType !== 'histogram' && plotType !== 'columns') {
          series.applyOptions({ color });
        }
      }
      setLineData(series, data.values);
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

      const setting  = indicatorSettings[bandKey] ?? DEFAULT_INDICATOR_SETTINGS[bandKey];
      const tfOk     = isVisibleForInterval(parentKey, interval as Interval);
      const visible  = (setting?.visible ?? false) && tfOk;
      if (!rawBands.length) return;

      const newSeries: ISeriesApi<'Line'>[] = [];
      for (const band of rawBands) {
        const uColor = setting?.color ?? band.upperColor;
        const lColor = setting?.color ?? band.lowerColor;
        const uStyle = setting?.lineStyle ?? 2;
        const u = makeLine(chart, uColor, 1, uStyle, visible);
        const l = makeLine(chart, lColor, 1, uStyle, visible);
        setLineData(u, band.upper);
        setLineData(l, band.lower);
        newSeries.push(u, l);
      }
      bandLines.set(bandKey, newSeries);
    };

    // Multi VWAP
    vwapData.multiPeriodVwaps.forEach(v => syncLine(v.name, v));

    // Daily VWAP
    syncLine('Daily VWAP',      vwapData.dailyVwap.current,  { lineWidth: 2 });
    syncLine('Prev Daily VWAP', vwapData.dailyVwap.previous, { lineStyle: 1 });
    syncBands('Daily VWAP Bands', vwapData.dailyVwap.bands, 'Daily VWAP');

    // Weekly VWAP
    syncLine('Weekly VWAP',      vwapData.weeklyVwap.current,  { lineWidth: 2 });
    syncLine('Prev Weekly VWAP', vwapData.weeklyVwap.previous, { lineStyle: 1 });
    syncBands('Weekly VWAP Bands', vwapData.weeklyVwap.bands, 'Weekly VWAP');

    // Sessions
    vwapData.sessions.forEach(session => {
      const lineKey = session.vwap.name;   // e.g. "Session Asia"
      const bandKey = lineKey + ' Bands';  // e.g. "Session Asia Bands"
      syncLine(lineKey, session.vwap, { lineWidth: 2 });
      syncBands(bandKey, session.bands, lineKey);
    });

    // VWMA Auto
    const vwmaKeys: string[] = [];
    (vwapData.vwapUltra1 ?? []).forEach(line => {
      syncLine(line.name, line, { lineWidth: indicatorSettings['VWMA Auto']?.lineWidth ?? 1 });
      vwmaKeys.push(line.name);
    });

    // VWMA MTF
    const mtfKeys: string[] = [];
    (vwapData.vwmaMtfMap ?? []).forEach(line => {
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
          color: parseFloat(k.c) >= parseFloat(k.o) ? 'rgba(14,203,129,0.35)' : 'rgba(246,70,93,0.35)',
        });
      }
    });
    return () => { unsub(); };
  }, [activeSymbol]);

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
    'Dollar Volume':  indicatorSettings['Dollar Volume']?.visible  ?? true,
    'Session Volume': indicatorSettings['Session Volume']?.visible ?? true,
    'Relative QV':    indicatorSettings['Relative QV']?.visible    ?? true,
    'ZScore':         indicatorSettings['ZScore']?.visible         ?? true,
  };

  const mainChart = chartRef.current;

  return (
    <div className="flex flex-col h-full w-full bg-[#000000] text-[#d1d4dc] overflow-hidden">
      {/* Interval toolbar */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#1a1a1a] bg-[#000000] shrink-0">
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

        <button
          onClick={() => setSettingsOpen(true)}
          title="Indicator settings"
          className="ml-auto p-1.5 rounded-md text-[#666] hover:text-white hover:bg-[#1a1a1a] transition-colors"
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
          <div ref={chartContainerRef} className="flex-1 min-h-[180px]" />

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
                {pane === 'Session Volume' && <SessionVolumeChart data={vwapData.sessionVolumeAccumulated} mainChart={mainChart} />}
                {pane === 'Relative QV'   && <RelativeQvChart    data={vwapData.relativeQv}               mainChart={mainChart} />}
                {pane === 'ZScore'        && <ZScoreChart        data={vwapData.zScore ?? []}             mainChart={mainChart} />}
              </DraggablePane>
            );
          })}
        </div>

        <IndicatorSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
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
      className="h-36 border-t border-[#111] shrink-0 flex flex-col relative bg-[#000000] group/pane"
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
    const onResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
      }
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      window.removeEventListener('resize', onResize);
      unsubSync();
      try { chart.remove(); } catch {}
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

// ── Sub-chart components ──────────────────────────────────────────────────────

function DollarVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#2196f3', priceLineVisible: false, lastValueVisible: true });
    hist.setData(data.perCandle.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color: '#2196f3',
    })));
    const sma = makeLine(chart, '#ffeb3b', 1, 0); setLineData(sma, data.sma30.values);
    const t1  = makeLine(chart, '#444',    1, 2);  setLineData(t1,  data.minimumThreshold.values);
    const t2  = makeLine(chart, '#2196f3', 1, 2);  setLineData(t2,  data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function SessionVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#4caf50', priceLineVisible: false, lastValueVisible: true });
    hist.setData(data.accumulated.values.filter((v: any) => v.value != null).map((v: any) => ({
      time: (v.time / 1000) as Time, value: v.value, color: '#4caf50',
    })));
    const t1 = makeLine(chart, '#444',    1, 2); setLineData(t1, data.minimumThreshold.values);
    const t2 = makeLine(chart, '#4caf50', 1, 2); setLineData(t2, data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function RelativeQvChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const line = makeLine(chart, '#ff9800', 2); setLineData(line, data.relative.values);
    const t1   = makeLine(chart, '#444', 1, 2); setLineData(t1,   data.minimumThreshold.values);
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
