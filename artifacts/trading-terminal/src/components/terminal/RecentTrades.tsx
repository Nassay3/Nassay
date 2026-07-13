import { useEffect, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { formatNumber } from '@/lib/format';
import { format } from 'date-fns';
import { wsManager } from '@/lib/ws';

export default function RecentTrades() {
  const { activeSymbol } = useTradingStore();
  const [trades, setTrades] = useState<any[]>([]);

  useEffect(() => {
    setTrades([]);
    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === 'aggTrade' && msg.s === activeSymbol) {
        setTrades(prev => {
          const next = [{
            id: msg.a || Math.random().toString(),
            price: msg.p,
            quantity: msg.q,
            time: msg.T,
            isBuyerMaker: msg.m
          }, ...prev];
          return next.slice(0, 30);
        });
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol]);

  return (
    <div className="flex h-full flex-col bg-card font-mono text-xs">
      <div className="flex items-center justify-between border-b border-border p-2 text-[10px] uppercase tracking-wide text-muted-foreground font-sans shrink-0">
        <span className="w-1/3 text-left">Price</span>
        <span className="w-1/3 text-right">Size</span>
        <span className="w-1/3 text-right">Time</span>
      </div>
      <div className="flex-1 overflow-auto p-1 flex flex-col gap-0.5">
        {trades.map((trade) => {
          const isSell = trade.isBuyerMaker; 
          return (
            <div key={trade.id} className="flex justify-between px-1 hover:bg-muted/50 cursor-pointer">
              <span className={`w-1/3 text-left ${isSell ? "text-danger" : "text-success"}`}>
                {formatNumber(trade.price, 2)}
              </span>
              <span className="text-foreground w-1/3 text-right">{formatNumber(trade.quantity, 4)}</span>
              <span className="text-muted-foreground w-1/3 text-right">{format(new Date(trade.time), 'HH:mm:ss')}</span>
            </div>
          );
        })}
        {trades.length === 0 && (
          <div className="p-4 text-center text-xs text-muted-foreground font-sans">
            Waiting for trades...
          </div>
        )}
      </div>
    </div>
  );
}
