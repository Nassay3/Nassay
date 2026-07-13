import React, { createContext, useContext, useState, useEffect } from 'react';
import { wsManager } from '@/lib/ws';

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w';

interface TradingContextType {
  activeSymbol: string;
  setActiveSymbol: (s: string) => void;
  interval: Interval;
  setInterval: (i: Interval) => void;
  activeIndicators: string[];
  toggleIndicator: (ind: string) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState<Interval>('1h');
  const [activeIndicators, setActiveIndicators] = useState<string[]>([
    'Multi VWAPs', 'Daily', 'Weekly', 'Sessions'
  ]);

  useEffect(() => {
    wsManager.connect();
  }, []);

  useEffect(() => {
    wsManager.subscribeToParams(activeSymbol, interval);
  }, [activeSymbol, interval]);

  const toggleIndicator = (ind: string) => {
    setActiveIndicators(prev =>
      prev.includes(ind) ? prev.filter(i => i !== ind) : [...prev, ind]
    );
  };

  return (
    <TradingContext.Provider value={{ 
      activeSymbol, 
      setActiveSymbol, 
      interval, 
      setInterval, 
      activeIndicators, 
      toggleIndicator 
    }}>
      {children}
    </TradingContext.Provider>
  );
}

export function useTradingStore() {
  const context = useContext(TradingContext);
  if (!context) throw new Error('useTradingStore must be used within TradingProvider');
  return context;
}
