import { useEffect, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { useGet24hrTicker, getGet24hrTickerQueryKey } from '@workspace/api-client-react';
import { formatNumber, formatVolume } from '@/lib/format';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { wsManager } from '@/lib/ws';

export default function TopBar() {
  const { activeSymbol } = useTradingStore();
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

  return (
    <div className="flex h-14 items-center justify-between border-b border-border bg-card px-4 text-sm shrink-0">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-foreground">{activeSymbol}</h1>
        </div>

        {ticker ? (
          <>
            <div className="flex flex-col">
              <span className={`text-base font-bold ${isPositive ? "text-success" : "text-danger"}`}>
                {formatNumber(ticker.lastPrice)}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono uppercase">${formatNumber(ticker.lastPrice)}</span>
            </div>

            <div className="flex flex-col">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">24h Change</span>
              <span className={`text-xs font-mono font-medium ${isPositive ? "text-success" : "text-danger"}`}>
                {isPositive ? '+' : ''}{formatNumber(ticker.priceChange)} ({formatNumber(ticker.priceChangePercent)}%)
              </span>
            </div>

            <div className="flex flex-col hidden sm:flex">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">24h High</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatNumber(ticker.highPrice)}</span>
            </div>

            <div className="flex flex-col hidden sm:flex">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">24h Low</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatNumber(ticker.lowPrice)}</span>
            </div>

            <div className="flex flex-col hidden md:flex">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">24h Vol(USDT)</span>
              <span className="text-xs font-mono font-medium text-foreground">{formatVolume(ticker.quoteVolume)}</span>
            </div>
          </>
        ) : (
           <div className="flex gap-6">
              {Array.from({length: 5}).map((_, i) => (
                <div key={i} className="flex flex-col gap-1">
                  <div className="h-3 w-16 animate-pulse bg-muted rounded"></div>
                  <div className="h-4 w-20 animate-pulse bg-muted rounded"></div>
                </div>
              ))}
           </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin text-primary' : ''}`} />
        </Button>
      </div>
    </div>
  );
}
