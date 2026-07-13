import React, { createContext, useContext, useState, useEffect } from 'react';
import { wsManager } from '@/lib/ws';

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w';

export interface IndicatorSetting {
  visible: boolean;
  color: string;
  lineWidth: 1 | 2 | 3;
  lineStyle: 0 | 1 | 2 | 3; // 0 solid, 1 dotted, 2 dashed, 3 large dashed
  filled?: boolean;
  fillColor?: string;
  period?: number;
}

export interface IndicatorSettings {
  [key: string]: IndicatorSetting;
}

export const DEFAULT_INDICATOR_SETTINGS: IndicatorSettings = {
  'VWAP 21': { visible: true, color: '#35e8ff', lineWidth: 1, lineStyle: 0 },
  'VWAP 48': { visible: true, color: '#f995ff', lineWidth: 1, lineStyle: 0 },
  'VWAP 84': { visible: true, color: '#acff35', lineWidth: 1, lineStyle: 0 },
  'VWAP 175': { visible: true, color: '#5b9cf6', lineWidth: 1, lineStyle: 0 },
  'VWAP 480': { visible: true, color: '#ffe0b2', lineWidth: 1, lineStyle: 0 },
  'VWAP 840': { visible: true, color: '#f3ff00', lineWidth: 1, lineStyle: 0 },
  'Daily VWAP': { visible: true, color: '#9598a1', lineWidth: 2, lineStyle: 0 },
  'Prev Daily VWAP': { visible: true, color: '#ff0000', lineWidth: 1, lineStyle: 0 },
  'Weekly VWAP': { visible: true, color: '#673ab7', lineWidth: 2, lineStyle: 0 },
  'Prev Weekly VWAP': { visible: true, color: '#ff0000', lineWidth: 1, lineStyle: 0 },
  'Session Asia': { visible: true, color: '#2962ff', lineWidth: 2, lineStyle: 0, filled: true, fillColor: 'rgba(41, 98, 255, 0.15)' },
  'Session London': { visible: true, color: '#9c27b0', lineWidth: 2, lineStyle: 0, filled: true, fillColor: 'rgba(156, 39, 176, 0.15)' },
  'Session NY': { visible: true, color: '#00c853', lineWidth: 2, lineStyle: 0, filled: true, fillColor: 'rgba(0, 200, 83, 0.15)' },
  'Session Daily': { visible: true, color: '#ff9100', lineWidth: 2, lineStyle: 0, filled: true, fillColor: 'rgba(255, 145, 0, 0.15)' },
  'Dollar Volume': { visible: true, color: '#2962ff', lineWidth: 1, lineStyle: 0 },
  'Session Volume': { visible: true, color: '#00c853', lineWidth: 1, lineStyle: 0 },
  'Relative QV': { visible: true, color: '#ff9100', lineWidth: 2, lineStyle: 0 },
};

interface TradingContextType {
  activeSymbol: string;
  setActiveSymbol: (s: string) => void;
  interval: Interval;
  setInterval: (i: Interval) => void;
  indicatorSettings: IndicatorSettings;
  updateIndicator: (name: string, patch: Partial<IndicatorSetting>) => void;
  resetIndicator: (name: string) => void;
  toggleIndicator: (name: string) => void;
  activeIndicatorNames: string[];
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState<Interval>('1h');
  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorSettings>(() => {
    try {
      const saved = localStorage.getItem('terminal_indicator_settings');
      return saved ? { ...DEFAULT_INDICATOR_SETTINGS, ...JSON.parse(saved) } : DEFAULT_INDICATOR_SETTINGS;
    } catch {
      return DEFAULT_INDICATOR_SETTINGS;
    }
  });

  useEffect(() => {
    wsManager.connect();
  }, []);

  useEffect(() => {
    wsManager.subscribeToParams(activeSymbol, interval);
  }, [activeSymbol, interval]);

  useEffect(() => {
    localStorage.setItem('terminal_indicator_settings', JSON.stringify(indicatorSettings));
  }, [indicatorSettings]);

  const updateIndicator = (name: string, patch: Partial<IndicatorSetting>) => {
    setIndicatorSettings(prev => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  };

  const resetIndicator = (name: string) => {
    setIndicatorSettings(prev => ({ ...prev, [name]: DEFAULT_INDICATOR_SETTINGS[name] }));
  };

  const toggleIndicator = (name: string) => {
    setIndicatorSettings(prev => ({ ...prev, [name]: { ...prev[name], visible: !prev[name]?.visible } }));
  };

  const activeIndicatorNames = Object.keys(indicatorSettings).filter(k => indicatorSettings[k].visible);

  return (
    <TradingContext.Provider value={{
      activeSymbol,
      setActiveSymbol,
      interval,
      setInterval,
      indicatorSettings,
      updateIndicator,
      resetIndicator,
      toggleIndicator,
      activeIndicatorNames,
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
