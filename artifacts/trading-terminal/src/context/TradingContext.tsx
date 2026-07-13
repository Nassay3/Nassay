import React, { createContext, useContext, useState, useEffect } from 'react';
import { wsManager } from '@/lib/ws';

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '6h' | '12h' | '1d' | '1w';

export const INTERVAL_LABELS: Record<Interval, string> = {
  '1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h',
  '4h': '4h', '6h': '6h', '12h': '12h', '1d': '1D', '1w': '1W',
};

// Visibility rules: which intervals an indicator group is visible on
// undefined = visible on all
export const INTERVAL_VISIBILITY: Record<string, Interval[]> = {
  'Daily VWAP':      ['1m', '5m', '15m', '1h'],
  'Prev Daily VWAP': ['1m', '5m', '15m', '1h'],
  'Weekly VWAP':     ['1m', '5m', '15m', '1h', '4h', '6h'],
  'Prev Weekly VWAP':['1m', '5m', '15m', '1h', '4h', '6h'],
  // Session VWAPs — handled by group name prefix in ChartPanel
};

/** Returns true if the given indicator key should be rendered for this interval */
export function isVisibleForInterval(key: string, interval: Interval): boolean {
  if (INTERVAL_VISIBILITY[key]) return INTERVAL_VISIBILITY[key].includes(interval);
  if (key.startsWith('Session ') && key !== 'Session Daily') {
    return interval === '1m' || interval === '5m';
  }
  return true;
}

export interface IndicatorSetting {
  visible: boolean;
  color: string;
  lineWidth: 1 | 2 | 3;
  lineStyle: 0 | 1 | 2 | 3;
  filled?: boolean;
  fillColor?: string;
}

export interface IndicatorSettings {
  [key: string]: IndicatorSetting;
}

export const DEFAULT_INDICATOR_SETTINGS: IndicatorSettings = {
  // Multi VWAP
  'VWAP 21':  { visible: true,  color: '#35e8ff', lineWidth: 1, lineStyle: 0 },
  'VWAP 48':  { visible: true,  color: '#f995ff', lineWidth: 1, lineStyle: 0 },
  'VWAP 84':  { visible: true,  color: '#acff35', lineWidth: 1, lineStyle: 0 },
  'VWAP 175': { visible: true,  color: '#5b9cf6', lineWidth: 1, lineStyle: 0 },
  'VWAP 480': { visible: true,  color: '#ffe0b2', lineWidth: 1, lineStyle: 0 },
  'VWAP 840': { visible: true,  color: '#f3ff00', lineWidth: 1, lineStyle: 0 },
  // Daily
  'Daily VWAP':      { visible: true,  color: '#9598a1', lineWidth: 2, lineStyle: 0 },
  'Prev Daily VWAP': { visible: true,  color: '#e91e63', lineWidth: 1, lineStyle: 1 },
  // Weekly
  'Weekly VWAP':      { visible: true,  color: '#673ab7', lineWidth: 2, lineStyle: 0 },
  'Prev Weekly VWAP': { visible: true,  color: '#ff5252', lineWidth: 1, lineStyle: 1 },
  // Sessions
  'Session Asia':   { visible: true,  color: '#f9a825', lineWidth: 2, lineStyle: 0 },
  'Session London': { visible: true,  color: '#9c27b0', lineWidth: 2, lineStyle: 0 },
  'Session NY':     { visible: true,  color: '#00e5ff', lineWidth: 2, lineStyle: 0 },
  'Session Daily':  { visible: true,  color: '#9598a1', lineWidth: 2, lineStyle: 0 },
  // Sub-panes
  'Dollar Volume':  { visible: true,  color: '#2196f3', lineWidth: 1, lineStyle: 0 },
  'Session Volume': { visible: true,  color: '#4caf50', lineWidth: 1, lineStyle: 0 },
  'Relative QV':    { visible: true,  color: '#ff9800', lineWidth: 2, lineStyle: 0 },
  'ZScore':         { visible: true,  color: '#ff9800', lineWidth: 1, lineStyle: 0 },
  // VWMA group (applied to all lines in the group)
  'VWMA Auto':      { visible: true,  color: '#acff35', lineWidth: 1, lineStyle: 0 },
  'VWMA MTF':       { visible: false, color: '#acff35', lineWidth: 1, lineStyle: 0 },
};

/** Sub-pane order state type */
export type SubPane = 'Dollar Volume' | 'Session Volume' | 'Relative QV' | 'ZScore';
export const DEFAULT_PANE_ORDER: SubPane[] = ['Dollar Volume', 'Session Volume', 'Relative QV', 'ZScore'];

interface TradingContextType {
  activeSymbol: string;
  setActiveSymbol: (s: string) => void;
  interval: Interval;
  setInterval: (i: Interval) => void;
  indicatorSettings: IndicatorSettings;
  updateIndicator: (name: string, patch: Partial<IndicatorSetting>) => void;
  resetIndicator: (name: string) => void;
  toggleIndicator: (name: string) => void;
  paneOrder: SubPane[];
  setPaneOrder: (order: SubPane[]) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT');
  const [interval, setInterval]         = useState<Interval>('1h');
  const [paneOrder, setPaneOrder]        = useState<SubPane[]>(DEFAULT_PANE_ORDER);

  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorSettings>(() => {
    try {
      const saved = localStorage.getItem('terminal_indicator_settings_v2');
      return saved ? { ...DEFAULT_INDICATOR_SETTINGS, ...JSON.parse(saved) } : DEFAULT_INDICATOR_SETTINGS;
    } catch {
      return DEFAULT_INDICATOR_SETTINGS;
    }
  });

  useEffect(() => { wsManager.connect(); }, []);
  useEffect(() => { wsManager.subscribeToParams(activeSymbol, interval); }, [activeSymbol, interval]);
  useEffect(() => {
    localStorage.setItem('terminal_indicator_settings_v2', JSON.stringify(indicatorSettings));
  }, [indicatorSettings]);

  const updateIndicator = (name: string, patch: Partial<IndicatorSetting>) =>
    setIndicatorSettings(prev => ({ ...prev, [name]: { ...prev[name], ...patch } }));

  const resetIndicator = (name: string) =>
    setIndicatorSettings(prev => ({ ...prev, [name]: DEFAULT_INDICATOR_SETTINGS[name] }));

  const toggleIndicator = (name: string) =>
    setIndicatorSettings(prev => ({ ...prev, [name]: { ...prev[name], visible: !prev[name]?.visible } }));

  return (
    <TradingContext.Provider value={{
      activeSymbol, setActiveSymbol,
      interval, setInterval,
      indicatorSettings, updateIndicator, resetIndicator, toggleIndicator,
      paneOrder, setPaneOrder,
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
