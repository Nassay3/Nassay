import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart, ColorType, IChartApi, ISeriesApi,
  Time, CandlestickSeries, HistogramSeries, LineSeries, CrosshairMode,
} from 'lightweight-charts';
import {
  useTradingStore, Interval, INTERVAL_LABELS, DEFAULT_INDICATOR_SETTINGS,
  isVisibleForInterval, SubPane,
} from '@/context/TradingContext';
import { useGetHistory, useGetVwap, getGetHistoryQueryKey, getGetVwapQueryKey } from '@workspace/api-client-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { wsManager } from '@/lib/ws';
import {
  Eye, EyeOff, Settings2, ChevronDown, ChevronRight, GripVertical,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

interface IndicatorGroup {
  label: string;
  keys: string[];
  settingKey?: string; // single key that controls group-level show/hide
  dynamicPrefix?: string; // prefix for dynamically-named lines (vwapUltra1 / vwmaMtfMap)
}

const INDICATOR_GROUPS: IndicatorGroup[] = [
  { label: 'Multi VWAP',   keys: ['VWAP 21','VWAP 48','VWAP 84','VWAP 175','VWAP 480','VWAP 840'] },
  { label: 'Daily',        keys: ['Daily VWAP','Prev Daily VWAP'] },
  { label: 'Weekly',       keys: ['Weekly VWAP','Prev Weekly VWAP'] },
  { label: 'Sessions',     keys: ['Session Asia','Session London','Session NY','Session Daily'] },
  { label: 'VWMA Auto',    keys: [],  settingKey: 'VWMA Auto',  dynamicPrefix: 'VWMA' },
  { label: 'VWMA MTF Map', keys: [],  settingKey: 'VWMA MTF',   dynamicPrefix: 'VWMA MTF' },
  { label: 'Sub-Panes',    keys: ['Dollar Volume','Session Volume','Relative QV','ZScore'] },
];

// ── Chart helpers ─────────────────────────────────────────────────────────────

function makeLine(
  chart: IChartApi,
  color: string,
  lineWidth: 1|2|3 = 1,
  lineStyle: 0|1|2|3 = 0,
  visible = true,
): ISeriesApi<'Line'> {
  return chart.addSeries(LineSeries, {
    color, lineWidth, lineStyle, visible,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    priceLineVisible: false,
  });
}

function setLineData(series: ISeriesApi<'Line'>, pts: {time: number; value: number|null}[]) {
  series.setData(
    pts.filter(p => p.value !== null)
       .map(p => ({ time: (p.time / 1000) as Time, value: p.value! })),
  );
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

// ── Main component ────────────────────────────────────────────────────────────

export default function ChartPanel() {
  const { activeSymbol, interval, setInterval, indicatorSettings, toggleIndicator, paneOrder, setPaneOrder } = useTradingStore();

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const seriesRefs        = useRef({
    candle:    null as ISeriesApi<'Candlestick'> | null,
    volume:    null as ISeriesApi<'Histogram'>   | null,
    vwapLines: new Map<string, ISeriesApi<'Line'>>(),
    vwapBands: new Map<string, ISeriesApi<'Line'>[]>(),
  });
  const seriesNameMap = useRef(new Map<ISeriesApi<any>, string>());
  const [hoveredValues, setHoveredValues]     = useState<Record<string, number>>({});
  const [expandedGroups, setExpandedGroups]   = useState<Record<string, boolean>>({});
  const [selectedKey, setSelectedKey]         = useState<string | null>(null);
  const [dynamicKeys, setDynamicKeys]         = useState<{ vwma: string[]; mtf: string[] }>({ vwma: [], mtf: [] });
  const dragPane = useRef<SubPane | null>(null);

  // --- Fetch historical klines and VWAP
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

  // ── 1. Init main chart ──────────────────────────────────────────────────────
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
      seriesRefs.current.vwapLines.clear();
      seriesRefs.current.vwapBands.clear();
      seriesNameMap.current.clear();
    };
  }, []);

  // ── 2. Load candle data ─────────────────────────────────────────────────────
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
        color: parseFloat(k.close) >= parseFloat(k.open)
          ? 'rgba(14,203,129,0.35)' : 'rgba(246,70,93,0.35)',
      })),
    );
  }, [klinesData]);

  // ── 3. Load VWAP data ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartRef.current || !vwapData) return;
    const chart = chartRef.current;
    const { vwapLines, vwapBands } = seriesRefs.current;

    const syncLine = (key: string, data: { color: string; values: {time:number;value:number|null}[] } | null | undefined, forcedSetting?: { color?: string; lineWidth?: 1|2|3; lineStyle?: 0|1|2|3 }) => {
      if (!data?.values) return;
      const setting    = indicatorSettings[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
      const tfVisible  = isVisibleForInterval(key, interval as Interval);
      const userVisible = setting?.visible ?? true;
      const visible    = userVisible && tfVisible;

      let series = vwapLines.get(key);
      if (!series) {
        series = makeLine(
          chart,
          forcedSetting?.color ?? setting?.color ?? data.color,
          forcedSetting?.lineWidth ?? setting?.lineWidth ?? 1,
          forcedSetting?.lineStyle ?? setting?.lineStyle ?? 0,
          visible,
        );
        vwapLines.set(key, series);
        seriesNameMap.current.set(series, key);
      }
      series.applyOptions({ visible });
      setLineData(series, data.values);
    };

    // Multi VWAP
    vwapData.multiPeriodVwaps.forEach(v => syncLine(v.name, v));

    // Daily (timeframe-filtered)
    syncLine('Daily VWAP',      vwapData.dailyVwap.current,  { lineWidth: 2 });
    syncLine('Prev Daily VWAP', vwapData.dailyVwap.previous, { lineStyle: 1 });

    // Weekly (timeframe-filtered)
    syncLine('Weekly VWAP',      vwapData.weeklyVwap.current,  { lineWidth: 2 });
    syncLine('Prev Weekly VWAP', vwapData.weeklyVwap.previous, { lineStyle: 1 });

    // Sessions — ONLY Daily session gets bands; Asia/London/NY → lines only
    vwapData.sessions.forEach(session => {
      const key = session.vwap.name; // e.g. "Session Asia", "Session Daily"
      syncLine(key, session.vwap, { lineWidth: 2 });

      // Remove old bands for this session
      const old = vwapBands.get(key);
      old?.forEach(b => chart.removeSeries(b));

      const sessUserVisible = (indicatorSettings[key]?.visible ?? true) && isVisibleForInterval(key, interval as Interval);

      // Only Daily session shows bands
      if (key === 'Session Daily' && session.bands.length) {
        const newBands: ISeriesApi<'Line'>[] = [];
        session.bands.forEach(band => {
          const mk = (pts: {time:number;value:number|null}[], color: string) => {
            const s = makeLine(chart, color, 1, 2, sessUserVisible);
            setLineData(s, pts);
            newBands.push(s);
          };
          mk(band.upper, band.upperColor);
          mk(band.lower, band.lowerColor);
        });
        vwapBands.set(key, newBands);
      } else {
        vwapBands.delete(key);
      }
    });

    // VWMA Auto (vwapUltra1)
    const vwmaKeys: string[] = [];
    (vwapData.vwapUltra1 ?? []).forEach(line => {
      syncLine(line.name, line, { lineWidth: indicatorSettings['VWMA Auto']?.lineWidth ?? 1 });
      vwmaKeys.push(line.name);
    });

    // VWMA MTF Map (vwmaMtfMap)
    const mtfKeys: string[] = [];
    (vwapData.vwmaMtfMap ?? []).forEach(line => {
      syncLine(line.name, line, { lineWidth: indicatorSettings['VWMA MTF']?.lineWidth ?? 1 });
      mtfKeys.push(line.name);
    });

    setDynamicKeys({ vwma: vwmaKeys, mtf: mtfKeys });

  }, [vwapData, interval]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 4. Apply settings changes ───────────────────────────────────────────────
  useEffect(() => {
    const { vwapLines, vwapBands } = seriesRefs.current;
    vwapLines.forEach((series, key) => {
      const setting   = indicatorSettings[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
      const tfVisible = isVisibleForInterval(key, interval as Interval);

      // Dynamic lines use group setting
      let groupKey = key;
      if (key.startsWith('VWMA ') && !key.includes('[')) groupKey = 'VWMA Auto';
      if (key.includes('['))                               groupKey = 'VWMA MTF';

      const gs = indicatorSettings[groupKey];
      const visible = (gs?.visible ?? setting?.visible ?? true) && tfVisible;
      series.applyOptions({
        visible,
        color:     gs?.color ?? setting?.color ?? '#ffffff',
        lineWidth: gs?.lineWidth ?? setting?.lineWidth ?? 1,
        lineStyle: gs?.lineStyle ?? setting?.lineStyle ?? 0,
      });
    });
    vwapBands.forEach((bands, key) => {
      const setting   = indicatorSettings[key];
      const tfVisible = isVisibleForInterval(key, interval as Interval);
      const visible   = (setting?.visible ?? true) && tfVisible;
      bands.forEach(b => b.applyOptions({ visible }));
    });
  }, [indicatorSettings, interval]);

  // ── 5. Live WebSocket ───────────────────────────────────────────────────────
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

  // ── Drag-to-reorder sub-panes ───────────────────────────────────────────────
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

  const mainChart = chartRef.current;

  // Pane visibility
  const paneVisible: Record<SubPane, boolean> = {
    'Dollar Volume':  indicatorSettings['Dollar Volume']?.visible  ?? true,
    'Session Volume': indicatorSettings['Session Volume']?.visible ?? true,
    'Relative QV':    indicatorSettings['Relative QV']?.visible    ?? true,
    'ZScore':         indicatorSettings['ZScore']?.visible         ?? true,
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#000000] text-[#d1d4dc] overflow-hidden">
      {/* ── Interval selector ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#1a1a1a] bg-[#000000] shrink-0">
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
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Indicator sidebar ──────────────────────────────────────────────── */}
        <IndicatorSidebar
          groups={INDICATOR_GROUPS}
          dynamicKeys={dynamicKeys}
          hoveredValues={hoveredValues}
          expandedGroups={expandedGroups}
          setExpandedGroups={setExpandedGroups}
          selectedKey={selectedKey}
          setSelectedKey={setSelectedKey}
          paneOrder={paneOrder}
          paneVisible={paneVisible}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDrop={() => { dragPane.current = null; }}
        />

        {/* ── Charts column ──────────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">
          <div ref={chartContainerRef} className="flex-1 min-h-[180px]" />

          {/* Draggable sub-panes */}
          {paneOrder.map(pane => {
            if (!paneVisible[pane] || !vwapData) return null;
            return (
              <DraggablePane
                key={pane}
                label={pane}
                onDragStart={() => handleDragStart(pane)}
                onDragOver={e => handleDragOver(e, pane)}
                onDrop={() => { dragPane.current = null; }}
              >
                {pane === 'Dollar Volume'  && <DollarVolumeChart  data={vwapData.dollarVolume}           mainChart={mainChart} />}
                {pane === 'Session Volume' && <SessionVolumeChart data={vwapData.sessionVolumeAccumulated} mainChart={mainChart} />}
                {pane === 'Relative QV'   && <RelativeQvChart    data={vwapData.relativeQv}              mainChart={mainChart} />}
                {pane === 'ZScore'        && <ZScoreChart        data={vwapData.zScore ?? []}            mainChart={mainChart} />}
              </DraggablePane>
            );
          })}
        </div>

        {/* ── Settings panel (slides in from right) ─────────────────────────── */}
        {selectedKey && (
          <SettingsPanel
            name={selectedKey}
            onClose={() => setSelectedKey(null)}
          />
        )}
      </div>
    </div>
  );
}

// ── Indicator Sidebar ─────────────────────────────────────────────────────────

function IndicatorSidebar({
  groups, dynamicKeys, hoveredValues, expandedGroups, setExpandedGroups,
  selectedKey, setSelectedKey, paneOrder, paneVisible, onDragStart, onDragOver, onDrop,
}: {
  groups: IndicatorGroup[];
  dynamicKeys: { vwma: string[]; mtf: string[] };
  hoveredValues: Record<string, number>;
  expandedGroups: Record<string, boolean>;
  setExpandedGroups: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  selectedKey: string | null;
  setSelectedKey: (k: string | null) => void;
  paneOrder: SubPane[];
  paneVisible: Record<SubPane, boolean>;
  onDragStart: (p: SubPane) => void;
  onDragOver: (e: React.DragEvent, p: SubPane) => void;
  onDrop: () => void;
}) {
  const { indicatorSettings, toggleIndicator } = useTradingStore();
  const { interval } = useTradingStore();

  const toggleGroup = (label: string) =>
    setExpandedGroups(prev => ({ ...prev, [label]: !prev[label] }));

  return (
    <div className="w-[195px] shrink-0 border-r border-[#1a1a1a] bg-[#080808] flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto no-scrollbar">
        {groups.map(group => {
          const isExpanded = expandedGroups[group.label] ?? true;

          // Resolve keys for dynamic groups
          let keys = [...group.keys];
          if (group.dynamicPrefix === 'VWMA') keys = dynamicKeys.vwma;
          if (group.dynamicPrefix === 'VWMA MTF') keys = dynamicKeys.mtf;

          // Sub-Panes group: render draggable rows
          if (group.label === 'Sub-Panes') {
            return (
              <div key={group.label} className="border-b border-[#111] mb-1">
                <GroupHeader label={group.label} isExpanded={isExpanded} onToggle={() => toggleGroup(group.label)} />
                {isExpanded && paneOrder.map(pane => {
                  const setting = indicatorSettings[pane];
                  const vis = paneVisible[pane];
                  return (
                    <div
                      key={pane}
                      draggable
                      onDragStart={() => onDragStart(pane)}
                      onDragOver={e => onDragOver(e, pane)}
                      onDrop={onDrop}
                      className="flex items-center justify-between px-2 py-1 hover:bg-[#111] group cursor-grab active:cursor-grabbing"
                    >
                      <div className="flex items-center gap-1.5 overflow-hidden">
                        <GripVertical size={10} className="text-[#333] shrink-0" />
                        <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: setting?.color ?? '#fff', opacity: vis ? 1 : 0.3 }} />
                        <span className={`text-[10px] truncate ${vis ? 'text-[#ccc]' : 'text-[#444]'}`}>{pane}</span>
                      </div>
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 shrink-0">
                        <button
                          onClick={e => { e.stopPropagation(); toggleIndicator(pane); }}
                          className="text-[#666] hover:text-white p-0.5 rounded"
                        >
                          {vis ? <Eye size={11} /> : <EyeOff size={11} />}
                        </button>
                        <button onClick={e => { e.stopPropagation(); setSelectedKey(pane); }} className="text-[#666] hover:text-white p-0.5 rounded">
                          <Settings2 size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          }

          // Group-level visibility key
          const groupSettingKey = group.settingKey;

          return (
            <div key={group.label} className="border-b border-[#111] mb-1">
              <GroupHeader
                label={group.label}
                isExpanded={isExpanded}
                onToggle={() => toggleGroup(group.label)}
                settingKey={groupSettingKey}
              />

              {isExpanded && keys.map(key => {
                const setting  = indicatorSettings[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
                const tfOk     = isVisibleForInterval(key, interval as Interval);
                const hovered  = hoveredValues[key];
                const effectiveVisible = (setting?.visible ?? true);

                return (
                  <div
                    key={key}
                    className="flex items-center justify-between px-2.5 py-1 hover:bg-[#111] group cursor-pointer"
                    onClick={() => setSelectedKey(key)}
                  >
                    <div className="flex items-center gap-1.5 overflow-hidden min-w-0">
                      <div
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{
                          backgroundColor: setting?.color ?? '#888',
                          opacity: effectiveVisible && tfOk ? 1 : 0.25,
                        }}
                      />
                      <div className="flex flex-col min-w-0">
                        <span className={`text-[10px] truncate leading-tight ${effectiveVisible && tfOk ? 'text-[#ccc]' : 'text-[#444]'}`}>
                          {key}
                        </span>
                        {hovered !== undefined && (
                          <span className="text-[9px] text-[#888] tabular-nums leading-tight">
                            {hovered.toFixed(2)}
                          </span>
                        )}
                        {!tfOk && (
                          <span className="text-[8px] text-[#444] leading-tight">hidden TF</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 shrink-0 ml-1">
                      <button
                        onClick={e => { e.stopPropagation(); toggleIndicator(key); }}
                        className="text-[#666] hover:text-white p-0.5 rounded"
                      >
                        {effectiveVisible ? <Eye size={11} /> : <EyeOff size={11} />}
                      </button>
                      <button onClick={e => { e.stopPropagation(); setSelectedKey(key); }} className="text-[#666] hover:text-white p-0.5 rounded">
                        <Settings2 size={11} />
                      </button>
                    </div>
                  </div>
                );
              })}

              {isExpanded && keys.length === 0 && group.dynamicPrefix && (
                <div className="px-3 py-1 text-[9px] text-[#333] italic">Loading…</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GroupHeader({ label, isExpanded, onToggle, settingKey }: {
  label: string; isExpanded: boolean; onToggle: () => void; settingKey?: string;
}) {
  const { indicatorSettings, toggleIndicator } = useTradingStore();
  const setting = settingKey ? indicatorSettings[settingKey] : undefined;

  return (
    <div className="flex items-center justify-between px-2.5 py-1.5 hover:bg-[#0f0f0f] cursor-pointer select-none group">
      <div className="flex items-center gap-1.5" onClick={onToggle}>
        {isExpanded ? <ChevronDown size={11} className="text-[#555]" /> : <ChevronRight size={11} className="text-[#555]" />}
        <span className="text-[10px] font-semibold text-[#888] tracking-wide uppercase">{label}</span>
      </div>
      {settingKey && (
        <button
          onClick={e => { e.stopPropagation(); toggleIndicator(settingKey); }}
          className="opacity-0 group-hover:opacity-100 text-[#555] hover:text-white p-0.5 rounded transition-opacity"
        >
          {setting?.visible !== false ? <Eye size={11} /> : <EyeOff size={11} />}
        </button>
      )}
    </div>
  );
}

// ── Settings Panel ────────────────────────────────────────────────────────────

function SettingsPanel({ name, onClose }: { name: string; onClose: () => void }) {
  const { indicatorSettings, updateIndicator, resetIndicator } = useTradingStore();
  const setting = indicatorSettings[name] ?? DEFAULT_INDICATOR_SETTINGS[name];
  const [tab, setTab] = useState<'inputs' | 'style' | 'visibility'>('style');

  if (!setting) return null;

  return (
    <div className="w-[220px] shrink-0 border-l border-[#1a1a1a] bg-[#0c0c0c] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1a1a1a] bg-[#101014]">
        <span className="text-[11px] font-bold text-[#d1d4dc] truncate">{name}</span>
        <button onClick={onClose} className="text-[#555] hover:text-white text-[18px] leading-none ml-2">×</button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#1a1a1a]">
        {(['style', 'visibility'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-[10px] font-medium transition-colors capitalize ${tab === t ? 'text-[#2962ff] border-b-2 border-[#2962ff]' : 'text-[#666] hover:text-[#999]'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto no-scrollbar p-3 flex flex-col gap-4 text-[11px]">
        {tab === 'style' && (
          <>
            {setting.color !== undefined && (
              <Row label="Color">
                <div className="flex items-center gap-2">
                  <input type="color" value={setting.color}
                    onChange={e => updateIndicator(name, { color: e.target.value })}
                    className="w-7 h-7 p-0 border-0 bg-transparent rounded cursor-pointer"
                  />
                  <span className="text-[10px] text-[#666] font-mono">{setting.color}</span>
                </div>
              </Row>
            )}
            {setting.lineWidth !== undefined && (
              <Row label={`Width: ${setting.lineWidth}px`}>
                <input type="range" min="1" max="3" value={setting.lineWidth}
                  onChange={e => updateIndicator(name, { lineWidth: parseInt(e.target.value) as any })}
                  className="w-full accent-[#2962ff]"
                />
              </Row>
            )}
            {setting.lineStyle !== undefined && (
              <Row label="Style">
                <select
                  value={setting.lineStyle}
                  onChange={e => updateIndicator(name, { lineStyle: parseInt(e.target.value) as any })}
                  className="w-full bg-[#101014] border border-[#2a2a2a] text-[#d1d4dc] p-1.5 rounded text-[11px] focus:outline-none focus:border-[#2962ff]"
                >
                  <option value={0}>Solid</option>
                  <option value={1}>Dotted</option>
                  <option value={2}>Dashed</option>
                  <option value={3}>Large Dashed</option>
                </select>
              </Row>
            )}
          </>
        )}
        {tab === 'visibility' && (
          <Row label="Show on chart">
            <button
              onClick={() => updateIndicator(name, { visible: !setting.visible })}
              className={`flex items-center gap-2 p-1.5 rounded transition-colors ${setting.visible ? 'text-[#2962ff]' : 'text-[#555]'}`}
            >
              {setting.visible ? <Eye size={16} /> : <EyeOff size={16} />}
              <span>{setting.visible ? 'Visible' : 'Hidden'}</span>
            </button>
          </Row>
        )}
      </div>

      {/* Footer */}
      <div className="flex gap-2 px-3 py-2 border-t border-[#1a1a1a] bg-[#101014]">
        <button onClick={onClose} className="flex-1 py-1.5 text-[11px] bg-[#2962ff] text-white rounded hover:bg-[#1e4fcf] transition-colors">
          OK
        </button>
        <button onClick={() => { resetIndicator(name); }} className="flex-1 py-1.5 text-[11px] bg-[#1a1a1a] text-[#999] rounded hover:bg-[#222] transition-colors">
          Reset
        </button>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] text-[#666]">{label}</span>
      {children}
    </div>
  );
}

// ── Draggable Sub-Pane wrapper ────────────────────────────────────────────────

function DraggablePane({ label, children, onDragStart, onDragOver, onDrop }: {
  label: string;
  children: React.ReactNode;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className="h-36 border-t border-[#111] shrink-0 flex flex-col relative bg-[#000000] group/pane"
    >
      <div className="absolute top-1 left-2 z-10 flex items-center gap-1">
        <GripVertical size={10} className="text-[#2a2a2a] cursor-grab group-hover/pane:text-[#444]" />
        <span className="text-[9px] text-[#555] font-bold uppercase tracking-wider">{label}</span>
      </div>
      {children}
    </div>
  );
}

// ── Sub-chart components ──────────────────────────────────────────────────────

function syncTimeScale(child: IChartApi, parent: IChartApi | null): () => void {
  if (!parent) return () => {};
  const ts = parent.timeScale();
  const sync = () => {
    try {
      const r = ts.getVisibleRange();
      if (r) child.timeScale().setVisibleRange(r);
    } catch (_) { /* chart may have been removed */ }
  };
  ts.subscribeVisibleTimeRangeChange(sync);
  sync();
  return () => { try { ts.unsubscribeVisibleTimeRangeChange(sync); } catch (_) {} };
}

function useSubChart(containerRef: React.RefObject<HTMLDivElement | null>, mainChart: IChartApi | null, build: (chart: IChartApi) => void, deps: any[]) {
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = subChartBase(containerRef.current as HTMLDivElement);
    build(chart);
    const unsubSync = syncTimeScale(chart, mainChart);
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
      try { chart.remove(); } catch (_) {}
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

function DollarVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#2196f3', priceLineVisible: false });
    hist.setData(data.perCandle.values.filter((v: any) => v.value != null).map((v: any) => ({ time: (v.time / 1000) as Time, value: v.value, color: '#2196f3' })));
    const smaLine = makeLine(chart, '#ffeb3b', 1, 0); setLineData(smaLine, data.sma30.values);
    const t1 = makeLine(chart, '#555', 1, 2);       setLineData(t1, data.minimumThreshold.values);
    const t2 = makeLine(chart, '#2196f3', 1, 2);    setLineData(t2, data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function SessionVolumeChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const hist = chart.addSeries(HistogramSeries, { color: '#4caf50', priceLineVisible: false });
    hist.setData(data.accumulated.values.filter((v: any) => v.value != null).map((v: any) => ({ time: (v.time / 1000) as Time, value: v.value })));
    const t1 = makeLine(chart, '#555', 1, 2);    setLineData(t1, data.minimumThreshold.values);
    const t2 = makeLine(chart, '#4caf50', 1, 2); setLineData(t2, data.optimalThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function RelativeQvChart({ data, mainChart }: { data: any; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    const line = makeLine(chart, '#ff9800', 2); setLineData(line, data.relative.values);
    const t1   = makeLine(chart, '#555', 1, 2); setLineData(t1, data.minimumThreshold.values);
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}

function ZScoreChart({ data, mainChart }: { data: any[]; mainChart: IChartApi | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useSubChart(ref, mainChart, (chart) => {
    data.forEach(line => {
      const s = makeLine(chart, line.color, 1); setLineData(s, line.values);
    });
    // Zero line
    const first = data[0]?.values?.[0];
    const last  = data[0]?.values?.[data[0].values.length - 1];
    if (first && last) {
      const zero = makeLine(chart, '#333', 1, 2);
      zero.setData([
        { time: (first.time / 1000) as Time, value: 0 },
        { time: (last.time  / 1000) as Time, value: 0 },
      ]);
    }
  }, [data, mainChart]);
  return <div ref={ref} className="flex-1 pt-4" />;
}
