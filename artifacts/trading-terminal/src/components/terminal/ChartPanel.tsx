import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, LineSeries, CrosshairMode } from 'lightweight-charts';
import { useTradingStore, Interval, DEFAULT_INDICATOR_SETTINGS } from '@/context/TradingContext';
import { useGetHistory, useGetVwap, getGetHistoryQueryKey, getGetVwapQueryKey } from '@workspace/api-client-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { wsManager } from '@/lib/ws';
import { Eye, EyeOff, Settings2, ChevronLeft } from 'lucide-react';

const INDICATOR_GROUPS = [
  { name: 'Multi VWAPs', keys: ['VWAP 21', 'VWAP 48', 'VWAP 84', 'VWAP 175', 'VWAP 480', 'VWAP 840'] },
  { name: 'Daily', keys: ['Daily VWAP', 'Prev Daily VWAP'] },
  { name: 'Weekly', keys: ['Weekly VWAP', 'Prev Weekly VWAP'] },
  { name: 'Sessions', keys: ['Session Asia', 'Session London', 'Session NY', 'Session Daily'] },
  { name: 'Volume & QV', keys: ['Dollar Volume', 'Session Volume', 'Relative QV'] }
];

export default function ChartPanel() {
  const { activeSymbol, interval, setInterval, indicatorSettings } = useTradingStore();
  
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  
  const seriesRefs = useRef({
    candle: null as ISeriesApi<"Candlestick"> | null,
    volume: null as ISeriesApi<"Histogram"> | null,
    vwapLines: new Map<string, ISeriesApi<"Line">>(),
    vwapBands: new Map<string, ISeriesApi<"Line">[]>(),
  });
  
  const seriesMap = useRef(new Map<ISeriesApi<any>, string>());
  const [hoveredValues, setHoveredValues] = useState<Record<string, number>>({});
  const [selectedIndicator, setSelectedIndicator] = useState<string | null>(null);

  const klinesParams = { symbol: activeSymbol, interval } as any;
  const { data: klinesData } = useGetHistory(
    klinesParams,
    { query: { queryKey: getGetHistoryQueryKey(klinesParams), refetchOnWindowFocus: false, staleTime: 60000 } }
  );

  const vwapParams = { symbol: activeSymbol, interval } as any;
  const { data: vwapData } = useGetVwap(
    vwapParams,
    { query: { queryKey: getGetVwapQueryKey(vwapParams), refetchOnWindowFocus: false, staleTime: 60000 } }
  );

  // 1. Initialize Main Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 11 },
      grid: { vertLines: { color: '#101014' }, horzLines: { color: '#101014' } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#1A1A1A' },
      rightPriceScale: { borderColor: '#1A1A1A', scaleMargins: { top: 0.1, bottom: 0.2 } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#2B2B36', style: 2, labelBackgroundColor: '#2962ff' }, horzLine: { color: '#2B2B36', style: 2, labelBackgroundColor: '#2962ff' } }
    });
    chartRef.current = chart;

    seriesRefs.current.candle = chart.addSeries(CandlestickSeries, {
      upColor: '#0ecb81', downColor: '#f6465d', borderVisible: false,
      wickUpColor: '#0ecb81', wickDownColor: '#f6465d',
    });

    seriesRefs.current.volume = chart.addSeries(HistogramSeries, {
      color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    chart.subscribeCrosshairMove((param) => {
       if (param.time) {
           const newValues: Record<string, number> = {};
           seriesMap.current.forEach((name, series) => {
               const data = param.seriesData.get(series);
               if (data && 'value' in data) {
                   newValues[name] = data.value as number;
               }
           });
           setHoveredValues(newValues);
       }
    });

    const handleResize = () => {
      if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRefs.current.candle = null;
      seriesRefs.current.volume = null;
      seriesRefs.current.vwapLines.clear();
      seriesRefs.current.vwapBands.clear();
      seriesMap.current.clear();
    };
  }, []);

  // 2. Set Kline Data
  useEffect(() => {
    if (!klinesData || !seriesRefs.current.candle) return;
    const formatted = klinesData.candles.map(k => ({
      time: (k.openTime / 1000) as Time,
      open: parseFloat(k.open),
      high: parseFloat(k.high),
      low: parseFloat(k.low),
      close: parseFloat(k.close)
    }));
    seriesRefs.current.candle.setData(formatted);

    if (seriesRefs.current.volume) {
      seriesRefs.current.volume.setData(klinesData.candles.map(k => ({
         time: (k.openTime / 1000) as Time, value: parseFloat(k.volume),
         color: parseFloat(k.close) >= parseFloat(k.open) ? 'rgba(14, 203, 129, 0.4)' : 'rgba(246, 70, 93, 0.4)'
      })));
    }
  }, [klinesData]);

  // 3. Set VWAP Data
  useEffect(() => {
    if (!chartRef.current || !vwapData) return;
    const chart = chartRef.current;
    const { vwapLines, vwapBands } = seriesRefs.current;

    const syncLine = (key: string, data: any) => {
        if (!data || !data.values) return;
        const setting = indicatorSettings[key] || DEFAULT_INDICATOR_SETTINGS[key];
        const isVisible = setting?.visible ?? false;
        
        let series = vwapLines.get(key);
        if (!series) {
            series = chart.addSeries(LineSeries, {
                color: setting?.color || data.color || '#ffffff',
                lineWidth: setting?.lineWidth || 1,
                lineStyle: setting?.lineStyle || 0,
                visible: isVisible,
                crosshairMarkerVisible: false,
                lastValueVisible: true,
                priceLineVisible: false,
            });
            vwapLines.set(key, series);
            seriesMap.current.set(series, key);
        }
        series.setData(data.values.filter((v: any) => v.value !== null).map((v: any) => ({ time: (v.time / 1000) as Time, value: v.value })));
    };

    vwapData.multiPeriodVwaps.forEach(vwap => syncLine(vwap.name.startsWith('VWAP') ? vwap.name : `VWAP ${vwap.name}`, vwap));
    syncLine('Daily VWAP', vwapData.dailyVwap.current);
    syncLine('Prev Daily VWAP', vwapData.dailyVwap.previous);
    syncLine('Weekly VWAP', vwapData.weeklyVwap.current);
    syncLine('Prev Weekly VWAP', vwapData.weeklyVwap.previous);

    vwapData.sessions.forEach(session => {
        const key = session.name.startsWith('Session') ? session.name : `Session ${session.name}`;
        syncLine(key, session.vwap);
        
        const setting = indicatorSettings[key];
        const isVisible = setting?.visible ?? false;
        
        const existingBands = vwapBands.get(key);
        if (existingBands) existingBands.forEach(b => chart.removeSeries(b));
        
        const newBands: ISeriesApi<"Line">[] = [];
        session.bands.forEach(band => {
            const createBand = (dataObj: any, color: string) => {
                const s = chart.addSeries(LineSeries, {
                    color: setting?.color || color,
                    lineWidth: 1, lineStyle: 2, visible: isVisible,
                    crosshairMarkerVisible: false, priceLineVisible: false,
                });
                s.setData(dataObj.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time / 1000) as Time, value: v.value })));
                return s;
            };
            newBands.push(createBand(band.upper, band.upperColor));
            newBands.push(createBand(band.lower, band.lowerColor));
        });
        vwapBands.set(key, newBands);
    });
  }, [vwapData]);

  // 4. Update Series Settings
  useEffect(() => {
   const { vwapLines, vwapBands } = seriesRefs.current;
   vwapLines.forEach((series, key) => {
       const setting = indicatorSettings[key];
       if (setting) {
           series.applyOptions({
               color: setting.color,
               lineWidth: setting.lineWidth,
               lineStyle: setting.lineStyle,
               visible: setting.visible,
           });
       }
   });
   vwapBands.forEach((bands, key) => {
       const setting = indicatorSettings[key];
       if (setting) {
           bands.forEach(band => band.applyOptions({
               color: setting.color,
               visible: setting.visible,
           }));
       }
   });
  }, [indicatorSettings]);

  // 5. Live WebSocket Updates
  useEffect(() => {
    if (!seriesRefs.current.candle) return;
    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === 'kline' && msg.s === activeSymbol) {
        const k = msg.k;
        const candle = {
          time: (k.t / 1000) as Time,
          open: parseFloat(k.o),
          high: parseFloat(k.h),
          low: parseFloat(k.l),
          close: parseFloat(k.c)
        };
        seriesRefs.current.candle?.update(candle);

        if (seriesRefs.current.volume) {
          seriesRefs.current.volume.update({
            time: (k.t / 1000) as Time,
            value: parseFloat(k.v),
            color: parseFloat(k.c) >= parseFloat(k.o) ? 'rgba(14, 203, 129, 0.4)' : 'rgba(246, 70, 93, 0.4)'
          });
        }
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol]);

  const showDollarVolume = indicatorSettings['Dollar Volume']?.visible;
  const showSessionVolume = indicatorSettings['Session Volume']?.visible;
  const showRelativeQv = indicatorSettings['Relative QV']?.visible;

  return (
    <div className="flex flex-col h-full w-full bg-[#000000] text-[#d1d4dc]">
      {/* Top Bar */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-[#1A1A1A] bg-[#000000] shrink-0">
        <ToggleGroup type="single" value={interval} onValueChange={(v) => v && setInterval(v as Interval)} size="sm">
          {['1m', '5m', '15m', '1h', '4h', '1d', '1w'].map(i => (
            <ToggleGroupItem key={i} value={i} className="h-6 px-2 text-[11px] data-[state=on]:bg-[#2962ff] data-[state=on]:text-white text-[#A3A6AF] hover:text-white hover:bg-[#1A1A1A] rounded transition-colors">
              {i}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      
      <div className="flex flex-1 overflow-hidden relative">
         {/* Left Sidebar for Indicators */}
         <div className="flex flex-col w-[200px] shrink-0 border-r border-[#1A1A1A] bg-[#0a0a0a]">
            {selectedIndicator ? (
                <IndicatorSettingsView name={selectedIndicator} onBack={() => setSelectedIndicator(null)} />
            ) : (
                <IndicatorListView onSelect={setSelectedIndicator} hoveredValues={hoveredValues} />
            )}
         </div>
         
         {/* Charts Container */}
         <div className="flex-1 flex flex-col min-w-0 bg-[#000000]">
            <div ref={chartContainerRef} className="flex-1 min-h-[200px]" />
            
            {showDollarVolume && vwapData && (
              <DollarVolumePane data={vwapData.dollarVolume} mainChart={chartRef.current} />
            )}
            
            {showSessionVolume && vwapData && (
              <SessionVolumePane data={vwapData.sessionVolumeAccumulated} mainChart={chartRef.current} />
            )}

            {showRelativeQv && vwapData && (
              <RelativeQvPane data={vwapData.relativeQv} mainChart={chartRef.current} />
            )}
         </div>
      </div>
    </div>
  );
}

// UI Components for Sidebar

function IndicatorListView({ onSelect, hoveredValues }: { onSelect: (name: string) => void, hoveredValues: Record<string, number> }) {
   const { indicatorSettings, toggleIndicator } = useTradingStore();

   return (
       <div className="flex-1 overflow-y-auto no-scrollbar bg-[#0a0a0a]">
           {INDICATOR_GROUPS.map(group => (
               <div key={group.name} className="border-b border-[#1A1A1A] pb-2 mb-2 last:border-0 mt-2">
                   <div className="px-3 py-1 text-[10px] text-[#555] font-bold tracking-wider">{group.name}</div>
                   {group.keys.map(key => {
                       const setting = indicatorSettings[key];
                       if (!setting) return null;
                       const value = hoveredValues[key];
                       return (
                           <div key={key} className="flex items-center justify-between px-3 py-1.5 hover:bg-[#1A1A1A] group cursor-pointer" onClick={() => onSelect(key)}>
                               <div className="flex items-center gap-2 overflow-hidden">
                                  <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: setting.color || '#fff', opacity: setting.visible ? 1 : 0.3 }} />
                                  <span className={`text-[11px] whitespace-nowrap truncate transition-colors ${setting.visible ? 'text-[#d1d4dc]' : 'text-[#555]'}`}>
                                     {key}
                                  </span>
                               </div>
                               <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                  <button onClick={(e) => { e.stopPropagation(); toggleIndicator(key); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                      {setting.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                                  </button>
                                  <button onClick={(e) => { e.stopPropagation(); onSelect(key); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                      <Settings2 size={12} />
                                  </button>
                               </div>
                           </div>
                       )
                   })}
               </div>
           ))}
       </div>
   )
}

function IndicatorSettingsView({ name, onBack }: { name: string; onBack: () => void }) {
    const { indicatorSettings, updateIndicator } = useTradingStore();
    const setting = indicatorSettings[name];

    if (!setting) return null;

    return (
        <div className="flex flex-col h-full bg-[#0a0a0a]">
            <div className="flex items-center gap-2 p-2 border-b border-[#1A1A1A] bg-[#101014]">
                <button onClick={onBack} className="p-1 hover:bg-[#1a1a1a] rounded text-[#A3A6AF] transition-colors"><ChevronLeft size={16} /></button>
                <div className="font-semibold text-[#d1d4dc] text-[11px] uppercase tracking-wider">{name}</div>
            </div>
            <div className="p-4 flex flex-col gap-5 text-[11px] text-[#A3A6AF] overflow-y-auto no-scrollbar">
                <div className="flex items-center justify-between">
                    <span>Visibility</span>
                    <button onClick={() => updateIndicator(name, { visible: !setting.visible })} className="p-1 hover:bg-[#1A1A1A] rounded transition-colors">
                        {setting.visible ? <Eye size={16} className="text-[#2962ff]" /> : <EyeOff size={16} />}
                    </button>
                </div>
                {setting.color !== undefined && (
                    <div className="flex items-center justify-between">
                        <span>Line Color</span>
                        <input type="color" value={setting.color} onChange={e => updateIndicator(name, { color: e.target.value })} className="w-6 h-6 p-0 border-0 bg-transparent rounded cursor-pointer" />
                    </div>
                )}
                {setting.lineWidth !== undefined && (
                    <div className="flex flex-col gap-2">
                        <div className="flex justify-between">
                           <span>Line Width</span>
                           <span className="text-[#d1d4dc]">{setting.lineWidth}px</span>
                        </div>
                        <input type="range" min="1" max="3" value={setting.lineWidth} onChange={e => updateIndicator(name, { lineWidth: parseInt(e.target.value) as any })} className="accent-[#2962ff]" />
                    </div>
                )}
                {setting.lineStyle !== undefined && (
                    <div className="flex flex-col gap-2">
                        <span>Line Style</span>
                        <select className="bg-[#101014] border border-[#2B2B36] text-[#d1d4dc] p-1.5 rounded focus:outline-none focus:border-[#2962ff]" value={setting.lineStyle} onChange={e => updateIndicator(name, { lineStyle: parseInt(e.target.value) as any })}>
                            <option value={0}>Solid</option>
                            <option value={1}>Dotted</option>
                            <option value={2}>Dashed</option>
                        </select>
                    </div>
                )}
                {setting.filled !== undefined && (
                    <div className="flex items-center justify-between mt-2 pt-4 border-t border-[#1A1A1A]">
                        <span>Fill Background</span>
                        <input type="checkbox" checked={setting.filled} onChange={e => updateIndicator(name, { filled: e.target.checked })} className="accent-[#2962ff] w-4 h-4 rounded border-[#2B2B36] bg-[#101014]" />
                    </div>
                )}
                {setting.filled && setting.fillColor !== undefined && (
                    <div className="flex flex-col gap-2">
                        <span>Fill Color (RGBA)</span>
                        <input type="text" value={setting.fillColor} onChange={e => updateIndicator(name, { fillColor: e.target.value })} className="bg-[#101014] border border-[#2B2B36] p-1.5 rounded text-center text-[#d1d4dc] focus:outline-none focus:border-[#2962ff]" />
                    </div>
                )}
            </div>
        </div>
    );
}

// Sub-Panes
function DollarVolumePane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 10 },
      grid: { vertLines: { color: '#101014' }, horzLines: { color: '#101014' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#1A1A1A' },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#2B2B36', style: 2 }, horzLine: { color: '#2B2B36', style: 2 } }
    });

    const hist = chart.addSeries(HistogramSeries, { color: data.perCandle.color, priceLineVisible: false });
    hist.setData(data.perCandle.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    const sma = chart.addSeries(LineSeries, { color: data.sma30.color, lineWidth: 1, crosshairMarkerVisible: false, priceLineVisible: false });
    sma.setData(data.sma30.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false });
      t1.setData(data.minimumThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }
    
    if (data.optimalThreshold) {
      const t2 = chart.addSeries(LineSeries, { color: data.optimalThreshold.color, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false });
      t2.setData(data.optimalThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }

    if (mainChart) {
      const timeScale = mainChart.timeScale();
      const syncRange = () => {
        const range = timeScale.getVisibleRange();
        if (range) chart.timeScale().setVisibleRange(range);
      };
      timeScale.subscribeVisibleTimeRangeChange(syncRange);
      syncRange();
    }

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, mainChart]);

  return (
    <div className="h-40 border-t border-[#1A1A1A] shrink-0 flex flex-col relative bg-[#000000]">
      <span className="absolute top-2 left-3 z-10 text-[10px] text-[#A3A6AF] font-bold uppercase tracking-wider">Dollar Volume</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}

function SessionVolumePane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 10 },
      grid: { vertLines: { color: '#101014' }, horzLines: { color: '#101014' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#1A1A1A' },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#2B2B36', style: 2 }, horzLine: { color: '#2B2B36', style: 2 } }
    });

    const hist = chart.addSeries(HistogramSeries, { color: data.accumulated.color, priceLineVisible: false });
    hist.setData(data.accumulated.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false });
      t1.setData(data.minimumThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }
    
    if (data.optimalThreshold) {
      const t2 = chart.addSeries(LineSeries, { color: data.optimalThreshold.color, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false });
      t2.setData(data.optimalThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }

    if (mainChart) {
      const timeScale = mainChart.timeScale();
      const syncRange = () => {
        const range = timeScale.getVisibleRange();
        if (range) chart.timeScale().setVisibleRange(range);
      };
      timeScale.subscribeVisibleTimeRangeChange(syncRange);
      syncRange();
    }

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, mainChart]);

  return (
    <div className="h-40 border-t border-[#1A1A1A] shrink-0 flex flex-col relative bg-[#000000]">
      <span className="absolute top-2 left-3 z-10 text-[10px] text-[#A3A6AF] font-bold uppercase tracking-wider">Session Volume</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}

function RelativeQvPane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000000' }, textColor: '#A3A6AF', fontSize: 10 },
      grid: { vertLines: { color: '#101014' }, horzLines: { color: '#101014' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#1A1A1A' },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#2B2B36', style: 2 }, horzLine: { color: '#2B2B36', style: 2 } }
    });

    const line = chart.addSeries(LineSeries, { color: data.relative.color, lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });
    line.setData(data.relative.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false });
      t1.setData(data.minimumThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }

    if (mainChart) {
      const timeScale = mainChart.timeScale();
      const syncRange = () => {
        const range = timeScale.getVisibleRange();
        if (range) chart.timeScale().setVisibleRange(range);
      };
      timeScale.subscribeVisibleTimeRangeChange(syncRange);
      syncRange();
    }

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, mainChart]);

  return (
    <div className="h-32 border-t border-[#1A1A1A] shrink-0 flex flex-col relative bg-[#000000]">
      <span className="absolute top-2 left-3 z-10 text-[10px] text-[#A3A6AF] font-bold uppercase tracking-wider">Relative QV</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}
