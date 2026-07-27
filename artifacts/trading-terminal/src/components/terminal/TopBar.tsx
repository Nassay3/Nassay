import { lazy, Suspense, useEffect, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { useGet24hrTicker, getGet24hrTickerQueryKey } from '@workspace/api-client-react';
import { formatNumber, formatVolume } from '@/lib/format';
import { RefreshCw, ChevronDown, Activity, TrendingUp, TrendingDown, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { wsManager } from '@/lib/ws';

const SymbolPicker = lazy(() => import('./SymbolPicker'));
const ChatPanel = lazy(() => import('./ChatPanel'));

export default function TopBar() {
  const { activeSymbol, marketType, setMarketType } = useTradingStore();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const tickerParams = { symbol: activeSymbol, market: marketType };
  const { data, refetch, isFetching } = useGet24hrTicker(
    tickerParams,
    { query: { queryKey: getGet24hrTickerQueryKey(tickerParams), refetchInterval: 60000 } }
  );

  const [liveTicker, setLiveTicker] = useState<any>(null);

  useEffect(() => {
    setLiveTicker(null);
  }, [activeSymbol, marketType]);

  useEffect(() => {
    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === '24hrTicker' && msg.s === activeSymbol) {
        setLiveTicker(msg);
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol, marketType]);

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
    <div className="flex h-12 items-center justify-between border-b border-[#252832] bg-[#101116] px-2.5 text-sm shrink-0 select-none shadow-[0_1px_0_rgba(255,255,255,0.02)]">
      <div className="flex items-center gap-4">
        <div className="flex h-8 shrink-0 items-center rounded-md border border-[#2b2e38] bg-[#15171d] p-0.5">
          {(['spot', 'futures'] as const).map((market) => (
            <button
              key={market}
              onClick={() => setMarketType(market)}
              className={`h-6 rounded px-2 text-[10px] font-semibold uppercase transition-colors ${
                marketType === market
                  ? 'bg-[#f0b90b] text-[#121318] shadow-sm'
                  : 'text-[#737b8a] hover:bg-[#222630] hover:text-white'
              }`}
              title={market === 'spot' ? 'Binance Global Spot' : 'Binance Global USD-M Futures'}
            >
              {market === 'spot' ? 'Spot' : 'Futures'}
            </button>
          ))}
        </div>

        {/* Symbol selector */}
        <button
          onClick={() => setPickerOpen(true)}
          className="flex h-8 items-center gap-2 px-2.5 rounded-md bg-[#191b22] border border-[#2b2e38] hover:border-[#4a4e5d] hover:bg-[#20232b] transition-colors group"
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
        <span className="hidden xl:inline text-[9px] font-semibold uppercase tracking-wider text-[#6f7785]">
          Binance Global · {marketType === 'spot' ? 'Spot' : 'USD‑M'}
        </span>
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

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-[#666] hover:text-[#2962ff] hover:bg-[#2962ff]/10"
          onClick={() => setChatOpen(true)}
        >
          <Sparkles size={18} />
        </Button>
      </div>

      <Suspense fallback={null}>
        {pickerOpen && <SymbolPicker open onClose={() => setPickerOpen(false)} />}
        {chatOpen && <ChatPanel open onClose={() => setChatOpen(false)} />}
      </Suspense>
    </div>
  );
}
