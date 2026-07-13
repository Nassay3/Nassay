#!/bin/bash
cat << 'INNER_EOF' > artifacts/trading-terminal/src/components/terminal/ChartPanel.tsx
import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, LineSeries, CrosshairMode } from 'lightweight-charts';
import { useTradingStore, Interval, IndicatorSetting, DEFAULT_INDICATOR_SETTINGS } from '@/context/TradingContext';
import { useGetHistory, useGetVwap, getGetHistoryQueryKey, getGetVwapQueryKey } from '@workspace/api-client-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { wsManager } from '@/lib/ws';
import { Eye, EyeOff, Settings2, ChevronLeft, ChevronDown, ChevronRight } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';

export default function ChartPanel() {
  const { activeSymbol, interval, setInterval, indicatorSettings, updateIndicator } = useTradingStore();
  
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

    const syncLine = (key: string, data: any, settingOverride?: IndicatorSetting, visibilityOverride?: boolean) => {
        if (!data || !data.values) return;
        const setting = settingOverride || indicatorSettings[key] || DEFAULT_INDICATOR_SETTINGS[key];
        const isVisible = visibilityOverride !== undefined ? visibilityOverride : (setting?.visible ?? false);
        
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
    
    vwapData.vwapUltra1?.forEach((vwap: any) => {
        const groupSetting = indicatorSettings['VWAP ULTRA1'];
        syncLine(vwap.name, vwap, groupSetting, groupSetting?.visible ?? true);
    });

    vwapData.vwmaMtfMap?.forEach((vwap: any) => {
        const match = vwap.name.match(/\[(.*?)\]/);
        const tf = match ? match[1] : '';
        const groupSetting = indicatorSettings['VWMA MTF Map'];
        const isVisible = (groupSetting?.visible ?? true) && (groupSetting?.subVisibilities?.[tf] ?? true);
        syncLine(vwap.name, vwap, groupSetting, isVisible);
    });

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
       let setting = indicatorSettings[key];
       let isVisible = setting?.visible;
       
       if (key.startsWith('VWAP ULTRA1')) {
           setting = indicatorSettings['VWAP ULTRA1'];
           isVisible = setting?.visible;
       } else if (key.startsWith('VWMA')) {
           setting = indicatorSettings['VWMA MTF Map'];
           const match = key.match(/\[(.*?)\]/);
           const tf = match ? match[1] : '';
           isVisible = (setting?.visible ?? true) && (setting?.subVisibilities?.[tf] ?? true);
       }
       
       if (setting) {
           series.applyOptions({
               color: setting.color,
               lineWidth: setting.lineWidth,
               lineStyle: setting.lineStyle,
               visible: isVisible,
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
            <IndicatorListView onSelect={setSelectedIndicator} hoveredValues={hoveredValues} vwapData={vwapData} />
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

      <SettingsModal 
        isOpen={!!selectedIndicator} 
        onClose={() => setSelectedIndicator(null)} 
        indicatorName={selectedIndicator} 
        setting={selectedIndicator ? indicatorSettings[selectedIndicator] : undefined}
        onSave={(patch) => selectedIndicator && updateIndicator(selectedIndicator, patch)} 
      />
    </div>
  );
}

// UI Components for Sidebar

function IndicatorListView({ onSelect, hoveredValues, vwapData }: { onSelect: (name: string) => void, hoveredValues: Record<string, number>, vwapData: any }) {
   const { indicatorSettings, toggleIndicator } = useTradingStore();
   
   const dynamicGroups = [
     { name: 'Multi VWAPs', isGroup: false, keys: ['VWAP 21', 'VWAP 48', 'VWAP 84', 'VWAP 175', 'VWAP 480', 'VWAP 840'] },
     { name: 'VWAP ULTRA1', isGroup: true, groupKey: 'VWAP ULTRA1', keys: vwapData?.vwapUltra1?.map((v:any) => v.name) || [] },
     { name: 'VWMA MTF Map', isGroup: true, groupKey: 'VWMA MTF Map', keys: vwapData?.vwmaMtfMap?.map((v:any) => v.name) || [] },
     { name: 'Daily', isGroup: false, keys: ['Daily VWAP', 'Prev Daily VWAP'] },
     { name: 'Weekly', isGroup: false, keys: ['Weekly VWAP', 'Prev Weekly VWAP'] },
     { name: 'Sessions', isGroup: false, keys: ['Session Asia', 'Session London', 'Session NY', 'Session Daily'] },
     { name: 'Volume & QV', isGroup: false, keys: ['Dollar Volume', 'Session Volume', 'Relative QV'] }
   ];

   const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

   return (
       <div className="flex-1 overflow-y-auto no-scrollbar bg-[#0a0a0a]">
           {dynamicGroups.map(group => {
               const isExpanded = expandedGroups[group.name] || !group.isGroup;
               return (
               <div key={group.name} className="border-b border-[#1A1A1A] pb-2 mb-2 last:border-0 mt-2">
                   <div 
                     className="px-3 py-1.5 flex items-center justify-between cursor-pointer group hover:bg-[#1A1A1A] transition-colors"
                     onClick={() => setExpandedGroups(prev => ({...prev, [group.name]: !prev[group.name]}))}
                   >
                       <div className="flex items-center gap-1.5 overflow-hidden">
                           {group.isGroup && (
                               <span className="text-[#555] shrink-0">
                                   {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                               </span>
                           )}
                           <div className="text-[10px] text-[#555] font-bold tracking-wider uppercase truncate">{group.name}</div>
                       </div>
                       
                       {group.isGroup && (
                           <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                               <button onClick={(e) => { e.stopPropagation(); toggleIndicator(group.groupKey!); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                   {indicatorSettings[group.groupKey!]?.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                               </button>
                               <button onClick={(e) => { e.stopPropagation(); onSelect(group.groupKey!); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                   <Settings2 size={12} />
                               </button>
                           </div>
                       )}
                   </div>
                   {isExpanded && group.keys.map((key: string) => {
                       const isGroupedLine = group.isGroup;
                       const setting = isGroupedLine ? indicatorSettings[group.groupKey!] : indicatorSettings[key];
                       if (!setting && !isGroupedLine) return null;
                       const color = setting?.color || '#fff';
                       
                       let visible = setting?.visible ?? false;
                       if (group.groupKey === 'VWMA MTF Map') {
                          const match = key.match(/\[(.*?)\]/);
                          if (match) {
                              visible = visible && (setting?.subVisibilities?.[match[1]] ?? true);
                          }
                       }

                       return (
                           <div key={key} className="flex items-center justify-between px-3 py-1.5 hover:bg-[#1A1A1A] group cursor-pointer" onClick={() => !isGroupedLine ? onSelect(key) : null}>
                               <div className="flex items-center gap-2 overflow-hidden pl-4">
                                 <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color, opacity: visible ? 1 : 0.3 }} />
                                 <span className={`text-[11px] whitespace-nowrap truncate transition-colors ${visible ? 'text-[#d1d4dc]' : 'text-[#555]'}`}>
                                     {key}
                                 </span>
                               </div>
                               <div className="flex items-center gap-2 shrink-0">
                                   <span className="text-[10px] text-[#A3A6AF] font-mono">
                                       {hoveredValues[key] ? hoveredValues[key].toFixed(2) : ''}
                                   </span>
                                   {!isGroupedLine && (
                                     <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                         <button onClick={(e) => { e.stopPropagation(); toggleIndicator(key); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                             {setting?.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                                         </button>
                                         <button onClick={(e) => { e.stopPropagation(); onSelect(key); }} className="text-[#A3A6AF] hover:text-white p-1 rounded hover:bg-[#2B2B36]">
                                             <Settings2 size={12} />
                                         </button>
                                     </div>
                                   )}
                               </div>
                           </div>
                       )
                   })}
               </div>
           )})}
       </div>
   )
}

const TIME_FRAMES = ['1M', '1W', '1D', '12h', '6h', '4h', '1h', '45m', '15m', '2m', '1m', '30s'];
const RANGES = ['Minutes', 'Hours', 'Days', 'Weeks', 'Months', 'Ranges'];

function SettingsModal({ 
  isOpen, 
  onClose, 
  indicatorName, 
  setting, 
  onSave 
}: { 
  isOpen: boolean, 
  onClose: () => void, 
  indicatorName: string | null, 
  setting?: IndicatorSetting,
  onSave: (patch: Partial<IndicatorSetting>) => void 
}) {
  const [localSetting, setLocalSetting] = useState<IndicatorSetting | undefined>(setting);

  useEffect(() => {
    if (isOpen && setting) {
      setLocalSetting(setting);
    }
  }, [isOpen, setting]);

  if (!localSetting || !indicatorName) return null;

  const handleSave = () => {
    onSave(localSetting);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[400px] bg-[#1e222d] border-[#2a2e39] text-[#d1d4dc] p-0 gap-0 shadow-2xl" dir="rtl">
        <DialogHeader className="px-5 py-3 border-b border-[#2a2e39] bg-[#131722] rounded-t-lg">
          <DialogTitle className="text-sm font-medium">{indicatorName}</DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="inputs" className="w-full" dir="rtl">
          <div className="px-5 bg-[#131722] border-b border-[#2a2e39]">
            <TabsList className="bg-transparent h-10 w-full justify-start gap-6 rounded-none p-0">
              <TabsTrigger value="inputs" className="data-[state=active]:bg-transparent data-[state=active]:text-[#2962ff] data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-[#2962ff] rounded-none px-0 h-10 text-xs font-medium text-[#787b86] hover:text-[#b2b5be]">مدخلات</TabsTrigger>
              <TabsTrigger value="style" className="data-[state=active]:bg-transparent data-[state=active]:text-[#2962ff] data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-[#2962ff] rounded-none px-0 h-10 text-xs font-medium text-[#787b86] hover:text-[#b2b5be]">نمط</TabsTrigger>
              <TabsTrigger value="visibility" className="data-[state=active]:bg-transparent data-[state=active]:text-[#2962ff] data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-[#2962ff] rounded-none px-0 h-10 text-xs font-medium text-[#787b86] hover:text-[#b2b5be]">ظهور</TabsTrigger>
            </TabsList>
          </div>

          <div className="p-5 max-h-[60vh] overflow-y-auto no-scrollbar">
            <TabsContent value="inputs" className="m-0 space-y-5">
              {indicatorName === 'VWMA MTF Map' ? (
                <div className="space-y-3">
                  <h3 className="text-xs text-[#d1d4dc] mb-2">إظهار أطر زمنية أعلى</h3>
                  <div className="grid grid-cols-3 gap-y-3 gap-x-2">
                    {TIME_FRAMES.map(tf => (
                      <label key={tf} className="flex items-center gap-2 text-xs text-[#787b86] cursor-pointer hover:text-[#d1d4dc] transition-colors">
                        <input 
                          type="checkbox" 
                          className="accent-[#2962ff] rounded-sm w-4 h-4 bg-[#1e222d] border-[#2a2e39] cursor-pointer"
                          checked={localSetting.subVisibilities?.[tf] ?? true}
                          onChange={e => setLocalSetting(s => ({
                            ...s!, 
                            subVisibilities: { ...s?.subVisibilities, [tf]: e.target.checked }
                          }))}
                        />
                        <span>{tf}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : (
                 <div className="space-y-3">
                   <h3 className="text-xs text-[#d1d4dc] mb-2">نطاقات التحديد</h3>
                   <div className="grid grid-cols-2 gap-y-3 gap-x-2">
                     {RANGES.map(r => (
                       <label key={r} className="flex items-center gap-2 text-xs text-[#787b86] cursor-pointer hover:text-[#d1d4dc] transition-colors">
                         <input type="checkbox" className="accent-[#2962ff] rounded-sm w-4 h-4 bg-[#1e222d] border-[#2a2e39] cursor-pointer" defaultChecked />
                         <span>{r}</span>
                       </label>
                     ))}
                   </div>
                 </div>
              )}
            </TabsContent>

            <TabsContent value="style" className="m-0 space-y-6">
              <div className="space-y-5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-[#787b86]">اللون</span>
                  <input type="color" value={localSetting.color} onChange={e => setLocalSetting(s => ({...s!, color: e.target.value}))} className="w-6 h-6 p-0 border-0 bg-transparent rounded cursor-pointer" />
                </div>
                
                <div className="space-y-3">
                  <div className="flex justify-between text-xs text-[#787b86]">
                    <span>سمك الخط</span>
                    <span className="text-[#d1d4dc]">{localSetting.lineWidth}</span>
                  </div>
                  <input type="range" min="1" max="3" value={localSetting.lineWidth} onChange={e => setLocalSetting(s => ({...s!, lineWidth: parseInt(e.target.value) as any}))} className="w-full accent-[#2962ff] h-1 bg-[#131722] rounded-lg appearance-none cursor-pointer" />
                </div>

                <div className="space-y-2">
                  <span className="text-xs text-[#787b86]">نمط الخط</span>
                  <select className="w-full bg-[#131722] border border-[#2a2e39] text-xs text-[#d1d4dc] p-2 rounded focus:outline-none focus:border-[#2962ff] cursor-pointer" value={localSetting.lineStyle} onChange={e => setLocalSetting(s => ({...s!, lineStyle: parseInt(e.target.value) as any}))}>
                    <option value={0}>متصل (Solid)</option>
                    <option value={1}>منقط (Dotted)</option>
                    <option value={2}>متقطع (Dashed)</option>
                  </select>
                </div>

                {localSetting.filled !== undefined && (
                  <label className="flex items-center justify-between text-xs text-[#787b86] cursor-pointer pt-4 border-t border-[#2a2e39] hover:text-[#d1d4dc] transition-colors">
                    <span>تعبئة الخلفية</span>
                    <input type="checkbox" checked={localSetting.filled} onChange={e => setLocalSetting(s => ({...s!, filled: e.target.checked}))} className="accent-[#2962ff] w-4 h-4 rounded-sm bg-[#1e222d] border-[#2a2e39] cursor-pointer" />
                  </label>
                )}
                {localSetting.filled && (
                  <div className="flex items-center justify-between pt-2">
                    <span className="text-xs text-[#787b86]">لون التعبئة</span>
                    <input type="text" value={localSetting.fillColor || ''} onChange={e => setLocalSetting(s => ({...s!, fillColor: e.target.value}))} className="bg-[#131722] border border-[#2a2e39] p-1.5 rounded text-center text-xs w-32 focus:outline-none focus:border-[#2962ff] text-left text-[#d1d4dc]" dir="ltr" />
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="visibility" className="m-0 space-y-4">
              <label className="flex items-center gap-2 text-xs text-[#787b86] cursor-pointer hover:text-[#d1d4dc] transition-colors">
                <input type="checkbox" checked={localSetting.visible} onChange={e => setLocalSetting(s => ({...s!, visible: e.target.checked}))} className="accent-[#2962ff] rounded-sm w-4 h-4 bg-[#1e222d] border-[#2a2e39] cursor-pointer" />
                <span>إظهار المؤشر</span>
              </label>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="px-5 py-3 border-t border-[#2a2e39] bg-[#131722] sm:justify-start gap-2 flex-row-reverse rounded-b-lg">
          <Button onClick={handleSave} className="bg-[#2962ff] hover:bg-[#1e53e5] text-white text-xs h-8 px-6 rounded-sm w-full sm:w-auto">موافق</Button>
          <Button onClick={onClose} variant="ghost" className="hover:bg-[#2a2e39] text-[#787b86] hover:text-[#d1d4dc] text-xs h-8 px-6 rounded-sm w-full sm:w-auto">إلغاء</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
INNER_EOF
sh update_chartpanel.sh
