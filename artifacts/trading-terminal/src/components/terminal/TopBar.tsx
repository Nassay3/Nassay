import { useEffect, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { useGet24hrTicker, getGet24hrTickerQueryKey } from '@workspace/api-client-react';
import { formatNumber, formatVolume } from '@/lib/format';
import { RefreshCw, ChevronDown, Activity, TrendingUp, TrendingDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { wsManager } from '@/lib/ws';
import SymbolPicker from './SymbolPicker';

export default function TopBar() {
  const { activeSymbol } = useTradingStore();
  const [pickerOpen, setPickerOpen] = useState(false);

  const tickerParams = { symbol: activeSymbol };
  const { data, refetch, isFetching } = useGet24hrTicker(
    tickerParams,
    { query: { queryKey: getGet24hrTickerQueryKey(tickerParams), refetchInterval: 60000 } }
  );

  const [liveTicker, setLiveTicker] = useState<any>(null);

  useEffect(() => {
    setLiveTicker(null);
  }, [activeSymbol]);

  useEffect(() => {
    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === '24hrTicker' && msg.s === activeSymbol) {
        setLiveTicker(msg);
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol]);

  const httpTicker = data?.tickers?.[0];
  const ticker = liveTicker ? {
    lastPrice: liveTicker.c,
    priceChange: liveTicker.p,
    priceChangePercent: liveTicker.P,
    highPrice: liveTicker.h,
    lowPrice: liveTicker.l,
    quoteVolume: liveTicker.q,
  } : httpTicker;

  const isPositive = ticker && parseFloat(ticker.priceChangePercent) >= 0;
  const baseSymbol = activeSymbol.replace('USDT', '');

  return (
    <div className="flex h-14 items-center justify-between border-b border-[#161616] bg-[#080808] px-3 text-sm shrink-0 select-none">
      <div className="flex items-center gap-4">
        {/* Symbol selector */}
        <button
          onClick={() => setPickerOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#111111] border border-[#222] hover:border-[#333] hover:bg-[#151515] transition-all group"
        >
          <div className="flex items-baseline gap-1">
            <span className="text-base font-bold text-foreground tracking-tight">{baseSymbol}</span>
            <span className="text-[11px] font-medium text-[#666]">/USDT</span>
          </div>
          <ChevronDown size={14} className="text-[#555] group-hover:text-[#888] transition-colors" />
        </button>

        {ticker ? (
          <div className="flex items-center gap-4">
            <div className="flex flex-col">
              <div className={`flex items-center gap-1.5 text-base font-bold font-mono ${isPositive ? 'text-[#0ecb81]' : 'text-[#f6465d]'}`}>
                {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {formatNumber(ticker.lastPrice)}
              </div>
              <span className="text-[10px] text-[#555] font-mono">${formatNumber(ticker.lastPrice)}</span>
            </div>

            <div className="hidden sm:flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-[#555]">24h Change</span>
              <span className={`text-xs font-mono font-medium ${isPositive ? 'text-[#0ecb81]' : 'text-[#f6465d]'}`}>
                {isPositive ? '+' : ''}{formatNumber(ticker.priceChange)} ({formatNumber(ticker.priceChangePercent)}%)
              </span>
            </div>

            <div className="hidden md:flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-[#555]">24h High</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatNumber(ticker.highPrice)}</span>
            </div>

            <div className="hidden md:flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-[#555]">24h Low</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatNumber(ticker.lowPrice)}</span>
            </div>

            <div className="hidden lg:flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-[#555]">24h Vol (USDT)</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatVolume(ticker.quoteVolume)}</span>
            </div>
          </div>
        ) : (
          <div className="flex gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1">
                <div className="h-3 w-16 animate-pulse bg-[#161616] rounded"></div>
                <div className="h-4 w-20 animate-pulse bg-[#161616] rounded"></div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#0d0d0d] border border-[#1a1a1a]">
          <Activity size={12} className={liveTicker ? 'text-[#0ecb81]' : 'text-[#555]'} />
          <span className="text-[10px] text-[#666] font-medium uppercase">
            {liveTicker ? 'Live' : 'Rest'}
          </span>
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-[#666] hover:text-foreground hover:bg-[#151515]"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin text-[#2962ff]' : ''}`} />
        </Button>
      </div>

      <SymbolPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </div>
  );
}
