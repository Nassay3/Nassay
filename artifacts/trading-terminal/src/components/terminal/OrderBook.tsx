import { useEffect, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { formatNumber } from '@/lib/format';
import { wsManager } from '@/lib/ws';

export default function OrderBook() {
  const { activeSymbol } = useTradingStore();
  const [asksMap, setAsksMap] = useState<Map<string, string>>(new Map());
  const [bidsMap, setBidsMap] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    setAsksMap(new Map());
    setBidsMap(new Map());

    const unsubscribe = wsManager.onMessage((msg) => {
      if (msg.e === 'depthUpdate' && msg.s === activeSymbol) {
        setAsksMap(prev => {
          const next = new Map(prev);
          if (msg.a) {
            msg.a.forEach(([price, qty]: [string, string]) => {
              if (parseFloat(qty) === 0) next.delete(price);
              else next.set(price, qty);
            });
          }
          return next;
        });
        setBidsMap(prev => {
          const next = new Map(prev);
          if (msg.b) {
            msg.b.forEach(([price, qty]: [string, string]) => {
              if (parseFloat(qty) === 0) next.delete(price);
              else next.set(price, qty);
            });
          }
          return next;
        });
      }
    });
    return () => { unsubscribe(); };
  }, [activeSymbol]);

  const asks = Array.from(asksMap.entries())
    .map(([price, qty]) => ({ price, quantity: qty }))
    .sort((a, b) => parseFloat(a.price) - parseFloat(b.price))
    .slice(0, 15)
    .reverse();

  const bids = Array.from(bidsMap.entries())
    .map(([price, qty]) => ({ price, quantity: qty }))
    .sort((a, b) => parseFloat(b.price) - parseFloat(a.price))
    .slice(0, 15);

  return (
    <div className="flex h-full flex-col bg-card font-mono text-xs">
      <div className="flex items-center justify-between border-b border-border p-2 text-[10px] uppercase tracking-wide text-muted-foreground font-sans shrink-0">
        <span className="w-1/3 text-left">Price</span>
        <span className="w-1/3 text-right">Size</span>
        <span className="w-1/3 text-right">Total</span>
      </div>
      <div className="flex-1 overflow-auto p-1 flex flex-col justify-center gap-1">
        {/* Asks */}
        <div className="flex flex-col gap-0.5 justify-end flex-1 min-h-0">
          {asks.map((ask, i) => {
            const total = parseFloat(ask.price) * parseFloat(ask.quantity);
            const depth = Math.min(100, (parseFloat(ask.quantity) / 2) * 100); 
            return (
              <div key={`ask-${i}`} className="relative flex justify-between px-1 hover:bg-muted/50 cursor-pointer group">
                <div className="absolute top-0 right-0 h-full bg-danger/10 z-0" style={{ width: `${depth}%` }} />
                <span className="text-danger z-10 w-1/3 text-left">{formatNumber(ask.price, 2)}</span>
                <span className="text-foreground z-10 w-1/3 text-right">{formatNumber(ask.quantity, 4)}</span>
                <span className="text-muted-foreground z-10 w-1/3 text-right">{formatNumber(total, 0)}</span>
              </div>
            );
          })}
        </div>

        {/* Spread / Last Price area */}
        <div className="flex items-center justify-center border-y border-border py-1 text-sm font-bold bg-background shrink-0">
          <span className="text-foreground">{bids[0] ? formatNumber(bids[0].price, 2) : '---'}</span>
        </div>

        {/* Bids */}
        <div className="flex flex-col gap-0.5 justify-start flex-1 min-h-0">
          {bids.map((bid, i) => {
            const total = parseFloat(bid.price) * parseFloat(bid.quantity);
            const depth = Math.min(100, (parseFloat(bid.quantity) / 2) * 100);
            return (
              <div key={`bid-${i}`} className="relative flex justify-between px-1 hover:bg-muted/50 cursor-pointer group">
                <div className="absolute top-0 right-0 h-full bg-success/10 z-0" style={{ width: `${depth}%` }} />
                <span className="text-success z-10 w-1/3 text-left">{formatNumber(bid.price, 2)}</span>
                <span className="text-foreground z-10 w-1/3 text-right">{formatNumber(bid.quantity, 4)}</span>
                <span className="text-muted-foreground z-10 w-1/3 text-right">{formatNumber(total, 0)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
