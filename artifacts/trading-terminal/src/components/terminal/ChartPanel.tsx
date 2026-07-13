import { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import { useTradingStore, Interval } from '@/context/TradingContext';
import { useGetHistory, useGetVwap, getGetHistoryQueryKey, getGetVwapQueryKey } from '@workspace/api-client-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Button } from '@/components/ui/button';
import { wsManager } from '@/lib/ws';

const ALL_INDICATORS = [
  'Multi VWAPs', 'Daily', 'Weekly', 'Sessions', 
  'Dollar Volume', 'Session Volume', 'R/QV'
];

export default function ChartPanel() {
  const { activeSymbol, interval, setInterval, activeIndicators, toggleIndicator } = useTradingStore();
  
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<{
    candleSeries?: ISeriesApi<any>;
    volumeSeries?: ISeriesApi<any>;
    vwapSeries: Array<{ category: string, series: ISeriesApi<any> }>;
  }>({ vwapSeries: [] });

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
      layout: { background: { type: ColorType.Solid, color: '#161A25' }, textColor: '#C3C6D4' },
      grid: { vertLines: { color: '#252B3B' }, horzLines: { color: '#252B3B' } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#252B3B' },
      rightPriceScale: { borderColor: '#252B3B', scaleMargins: { top: 0.1, bottom: 0.2 } },
      crosshair: { mode: 1, vertLine: { color: '#4c525e', style: 0 }, horzLine: { color: '#4c525e', style: 0 } }
    });
    chartRef.current = chart;

    seriesRefs.current.candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#0ecb81', downColor: '#f6465d', borderVisible: false,
      wickUpColor: '#0ecb81', wickDownColor: '#f6465d',
    });

    seriesRefs.current.volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '',
    });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const handleResize = () => {
      if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRefs.current.candleSeries = undefined;
      seriesRefs.current.volumeSeries = undefined;
      seriesRefs.current.vwapSeries = [];
    };
  }, []);

  // 2. Set Kline Data
  useEffect(() => {
    if (!klinesData || !seriesRefs.current.candleSeries) return;
    const formatted = klinesData.candles.map(k => ({
      time: (k.openTime / 1000) as Time,
      open: parseFloat(k.open),
      high: parseFloat(k.high),
      low: parseFloat(k.low),
      close: parseFloat(k.close)
    }));
    seriesRefs.current.candleSeries.setData(formatted);

    if (seriesRefs.current.volumeSeries) {
      seriesRefs.current.volumeSeries.setData(klinesData.candles.map(k => ({
         time: (k.openTime / 1000) as Time, value: parseFloat(k.volume),
         color: parseFloat(k.close) >= parseFloat(k.open) ? 'rgba(14, 203, 129, 0.4)' : 'rgba(246, 70, 93, 0.4)'
      })));
    }
  }, [klinesData]);

  // 3. Set VWAP Data on Main Chart
  const prevVwapDataRef = useRef<any>(null);
  useEffect(() => {
    if (!chartRef.current || !vwapData) return;
    if (prevVwapDataRef.current === vwapData) return;
    prevVwapDataRef.current = vwapData;

    if (seriesRefs.current.vwapSeries) {
      seriesRefs.current.vwapSeries.forEach(s => chartRef.current?.removeSeries(s.series));
    }
    seriesRefs.current.vwapSeries = [];

    const addLine = (lineData: any, color: string, lineWidth: 1 | 2 | 3 | 4 = 1, category = '', lineStyle = 0) => {
      if (!lineData || !lineData.values) return null;
      const s = chartRef.current!.addSeries(LineSeries, { color, lineWidth, lineStyle, crosshairMarkerVisible: false });
      s.setData(lineData.values.filter((v: any) => v.value !== null).map((v: any) => ({ time: (v.time / 1000) as Time, value: v.value })));
      seriesRefs.current.vwapSeries.push({ category, series: s });
      return s;
    };

    vwapData.multiPeriodVwaps.forEach(vwap => addLine(vwap, vwap.color, 1, 'Multi VWAPs'));
    
    addLine(vwapData.dailyVwap.previous, vwapData.dailyVwap.previous.color, 1, 'Daily');
    addLine(vwapData.dailyVwap.current, vwapData.dailyVwap.current.color, 2, 'Daily');

    addLine(vwapData.weeklyVwap.previous, vwapData.weeklyVwap.previous.color, 1, 'Weekly');
    addLine(vwapData.weeklyVwap.current, vwapData.weeklyVwap.current.color, 2, 'Weekly');

    vwapData.sessions.forEach(session => {
      addLine(session.vwap, session.vwap.color, 2, 'Sessions');
      session.bands.forEach(band => {
        const u = chartRef.current!.addSeries(LineSeries, { color: band.upperColor, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false });
        u.setData(band.upper.filter(v => v.value !== null).map(v => ({ time: (v.time / 1000) as Time, value: v.value })));
        seriesRefs.current.vwapSeries.push({ category: 'Sessions', series: u });

        const l = chartRef.current!.addSeries(LineSeries, { color: band.lowerColor, lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false });
        l.setData(band.lower.filter(v => v.value !== null).map(v => ({ time: (v.time / 1000) as Time, value: v.value })));
        seriesRefs.current.vwapSeries.push({ category: 'Sessions', series: l });
      });
    });

  }, [vwapData]);

  // 4. Update Series Visibility on Main Chart
  useEffect(() => {
    if (seriesRefs.current.vwapSeries) {
      seriesRefs.current.vwapSeries.forEach(item => {
        item.series.applyOptions({ visible: activeIndicators.includes(item.category) });
      });
    }
  }, [activeIndicators, vwapData]);

  // 5. Live WebSocket Updates for Kline
  useEffect(() => {
    if (!seriesRefs.current.candleSeries) return;
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
        seriesRefs.current.candleSeries?.update(candle);

        if (seriesRefs.current.volumeSeries) {
          seriesRefs.current.volumeSeries.update({
            time: (k.t / 1000) as Time,
            value: parseFloat(k.v),
            color: parseFloat(k.c) >= parseFloat(k.o) ? 'rgba(14, 203, 129, 0.4)' : 'rgba(246, 70, 93, 0.4)'
          });
        }
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol]);

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-center gap-4 border-b border-border p-2 shrink-0 overflow-x-auto no-scrollbar">
        <ToggleGroup type="single" value={interval} onValueChange={(v) => v && setInterval(v as Interval)} size="sm">
          {['1m', '5m', '15m', '1h', '4h', '1d', '1w'].map(i => (
            <ToggleGroupItem key={i} value={i} className="text-xs h-7">{i}</ToggleGroupItem>
          ))}
        </ToggleGroup>

        <div className="h-4 w-[1px] bg-border shrink-0"></div>

        <div className="flex items-center gap-1">
          {ALL_INDICATORS.map(ind => (
            <Button
              key={ind}
              variant={activeIndicators.includes(ind) ? "secondary" : "ghost"}
              size="sm"
              className="h-7 text-xs px-2 whitespace-nowrap"
              onClick={() => toggleIndicator(ind)}
            >
              {ind}
            </Button>
          ))}
        </div>
      </div>
      
      <div className="flex flex-col flex-1 overflow-hidden">
        <div ref={chartContainerRef} className="flex-1 min-h-[200px]" />
        
        {activeIndicators.includes('Dollar Volume') && vwapData && (
          <DollarVolumePane data={vwapData.dollarVolume} mainChart={chartRef.current} />
        )}
        
        {activeIndicators.includes('Session Volume') && vwapData && (
          <SessionVolumePane data={vwapData.sessionVolumeAccumulated} mainChart={chartRef.current} />
        )}

        {activeIndicators.includes('R/QV') && vwapData && (
          <RelativeQvPane data={vwapData.relativeQv} mainChart={chartRef.current} />
        )}
      </div>
    </div>
  );
}

// Sub-Panes
function DollarVolumePane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#161A25' }, textColor: '#C3C6D4' },
      grid: { vertLines: { color: '#252B3B' }, horzLines: { color: '#252B3B' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#252B3B' },
      crosshair: { mode: 1 }
    });
    chartRef.current = chart;

    const hist = chart.addSeries(HistogramSeries, { color: data.perCandle.color });
    hist.setData(data.perCandle.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    const sma = chart.addSeries(LineSeries, { color: data.sma30.color, lineWidth: 1 });
    sma.setData(data.sma30.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2 });
      t1.setData(data.minimumThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }
    
    if (data.optimalThreshold) {
      const t2 = chart.addSeries(LineSeries, { color: data.optimalThreshold.color, lineWidth: 1, lineStyle: 2 });
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
    <div className="h-40 border-t border-border shrink-0 flex flex-col relative">
      <span className="absolute top-1 left-2 z-10 text-[10px] text-muted-foreground font-mono">Dollar Volume</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}

function SessionVolumePane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#161A25' }, textColor: '#C3C6D4' },
      grid: { vertLines: { color: '#252B3B' }, horzLines: { color: '#252B3B' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#252B3B' },
      crosshair: { mode: 1 }
    });

    const hist = chart.addSeries(HistogramSeries, { color: data.accumulated.color });
    hist.setData(data.accumulated.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2 });
      t1.setData(data.minimumThreshold.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));
    }
    
    if (data.optimalThreshold) {
      const t2 = chart.addSeries(LineSeries, { color: data.optimalThreshold.color, lineWidth: 1, lineStyle: 2 });
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
    <div className="h-40 border-t border-border shrink-0 flex flex-col relative">
      <span className="absolute top-1 left-2 z-10 text-[10px] text-muted-foreground font-mono">Session Volume Accumulated</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}

function RelativeQvPane({ data, mainChart }: { data: any, mainChart: IChartApi | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#161A25' }, textColor: '#C3C6D4' },
      grid: { vertLines: { color: '#252B3B' }, horzLines: { color: '#252B3B' } },
      timeScale: { visible: false },
      rightPriceScale: { borderColor: '#252B3B' },
      crosshair: { mode: 1 }
    });

    const line = chart.addSeries(LineSeries, { color: data.relative.color, lineWidth: 2 });
    line.setData(data.relative.values.filter((v:any) => v.value !== null).map((v:any) => ({ time: (v.time/1000) as Time, value: v.value })));

    if (data.minimumThreshold) {
      const t1 = chart.addSeries(LineSeries, { color: data.minimumThreshold.color, lineWidth: 1, lineStyle: 2 });
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
    <div className="h-32 border-t border-border shrink-0 flex flex-col relative">
      <span className="absolute top-1 left-2 z-10 text-[10px] text-muted-foreground font-mono">Relative QV</span>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}
