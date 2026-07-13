import { useState, useEffect } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { useListSymbols, useGet24hrTicker, getGet24hrTickerQueryKey } from '@workspace/api-client-react';
import { formatNumber, formatVolume } from '@/lib/format';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { wsManager } from '@/lib/ws';

export default function Watchlist() {
  const { activeSymbol, setActiveSymbol } = useTradingStore();
  const [search, setSearch] = useState('');

  const { data: symbolsData, isLoading: loadingSymbols } = useListSymbols({ quote: 'USDT' });
  const tickerParams = undefined;
  const { data: tickersData, isLoading: loadingTickers } = useGet24hrTicker(tickerParams, {
    query: { queryKey: getGet24hrTickerQueryKey(tickerParams), refetchInterval: 10000 }
  });

  const [liveTickers, setLiveTickers] = useState<Record<string, any>>({});

  useEffect(() => {
    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === '24hrTicker') {
        setLiveTickers(prev => ({ ...prev, [msg.s]: msg }));
      }
    });
    return () => { unsubscribe(); };
  }, []);

  const usdtSymbols = new Set(symbolsData?.symbols.map(s => s.symbol) || []);
  
  const baseWatchlist = (tickersData?.tickers || [])
    .filter(t => usdtSymbols.has(t.symbol) && t.symbol.toLowerCase().includes(search.toLowerCase()))
    .map(t => {
      const live = liveTickers[t.symbol];
      return live ? {
        ...t,
        lastPrice: live.c,
        priceChangePercent: live.P,
        quoteVolume: live.q
      } : t;
    })
    .sort((a, b) => parseFloat(b.quoteVolume) - parseFloat(a.quoteVolume));

  if (loadingSymbols || loadingTickers) {
    return (
      <div className="p-4 flex flex-col gap-3 h-full bg-card">
        <Skeleton className="h-8 w-full"/>
        <Skeleton className="h-10 w-full"/>
        <Skeleton className="h-10 w-full"/>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="p-2 border-b border-border shrink-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8 text-xs bg-background border-border"
          />
        </div>
      </div>
      <div className="flex items-center justify-between border-b border-border p-2 text-[10px] uppercase tracking-wide text-muted-foreground font-sans shrink-0">
        <span className="w-1/3 text-left">Pair</span>
        <span className="w-1/3 text-right">Price</span>
        <span className="w-1/3 text-right">Change</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {baseWatchlist.map(t => {
          const isPositive = parseFloat(t.priceChangePercent) >= 0;
          const isActive = activeSymbol === t.symbol;
          return (
            <div
              key={t.symbol}
              onClick={() => setActiveSymbol(t.symbol)}
              className={`flex cursor-pointer items-center justify-between p-2 px-3 text-xs font-mono hover:bg-muted/50 transition-colors ${isActive ? 'bg-muted border-l-2 border-primary' : 'border-l-2 border-transparent'}`}
            >
              <div className="flex flex-col gap-0.5 w-1/3">
                <span className="font-bold text-foreground">{t.symbol.replace('USDT', '')}</span>
                <span className="text-[10px] text-muted-foreground">{formatVolume(t.quoteVolume)}</span>
              </div>
              <div className="flex flex-col items-end gap-0.5 w-1/3">
                <span className={isPositive ? "text-success" : "text-danger"}>
                  {formatNumber(t.lastPrice)}
                </span>
              </div>
              <div className="flex flex-col items-end gap-0.5 w-1/3">
                <span className={`text-[10px] px-1 py-0.5 rounded ${isPositive ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}>
                  {isPositive ? '+' : ''}{formatNumber(t.priceChangePercent)}%
                </span>
              </div>
            </div>
          );
        })}
        {baseWatchlist.length === 0 && (
          <div className="p-4 text-center text-xs text-muted-foreground">
            No symbols found.
          </div>
        )}
      </div>
    </div>
  );
}
