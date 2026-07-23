import React, { createContext, useContext, useState, useEffect } from 'react';
import { wsManager } from '@/lib/ws';

export type Interval = '5s' | '15s' | '30s' | '1m' | '2m' | '5m' | '15m' | '30m' | '45m' | '1h' | '4h' | '6h' | '12h' | '1d' | '1w' | '1M' | '3M';

/** Plot type matching TradingView's line style menu */
export type PlotType =
  | 'line' | 'line-broken' | 'gradient' | 'step' | 'step-broken' | 'gradient-markers'
  | 'histogram' | 'cross' | 'area' | 'area-broken' | 'columns' | 'circles';

export const PLOT_TYPE_LABELS: Record<PlotType, { ar: string; en: string }> = {
  'line':            { ar: 'خط',                         en: 'Line' },
  'line-broken':     { ar: 'خط ذو فواصل',                en: 'Line with breaks' },
  'gradient':        { ar: 'خط متدرج',                   en: 'Gradient line' },
  'step':            { ar: 'خط خطوة',                    en: 'Step line' },
  'step-broken':     { ar: 'خط خطوة مع فواصل',          en: 'Step line with breaks' },
  'gradient-markers':{ ar: 'متدرج مع معينات',           en: 'Gradient with markers' },
  'histogram':       { ar: 'المدرج الإحصائي',            en: 'Histogram' },
  'cross':           { ar: 'تقاطع',                      en: 'Cross' },
  'area':            { ar: 'مساحة',                      en: 'Area' },
  'area-broken':     { ar: 'مساحة يتخللها فواصل',        en: 'Area with breaks' },
  'columns':         { ar: 'القيم الأعمدة',              en: 'Columns' },
  'circles':         { ar: 'دوائر',                      en: 'Circles' },
};

export const INTERVAL_LABELS: Record<Interval, string> = {
  '5s': '5s', '15s': '15s', '30s': '30s', '1m': '1m', '2m': '2m', '5m': '5m', '15m': '15m', '30m': '30m', '45m': '45m', '1h': '1h',
  '4h': '4h', '6h': '6h', '12h': '12h', '1d': '1D', '1w': '1W', '1M': '1M', '3M': '3M',
};

// Timeframe visibility rules for overlay VWAPs
export const INTERVAL_VISIBILITY: Record<string, Interval[]> = {
  'Daily VWAP':       ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Prev Daily VWAP':  ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Weekly VWAP':      ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Prev Weekly VWAP': ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
};

export function isVisibleForInterval(key: string, interval: Interval): boolean {
  if (INTERVAL_VISIBILITY[key]) return INTERVAL_VISIBILITY[key].includes(interval);
  // Session Asia/London/NY are intraday-only, as in the Pine session script.
  if (key.startsWith('Session ') && key !== 'Session Daily') {
    return !['1d', '1w', '1M', '3M'].includes(interval);
  }
  return true;
}

export interface IndicatorSetting {
  visible: boolean;
  color: string;
  lineWidth: 1 | 2 | 3;
  lineStyle: 0 | 1 | 2 | 3;
  plotType?: PlotType;
}

export interface IndicatorSettings {
  [key: string]: IndicatorSetting;
}

function s(visible: boolean, color: string, lineWidth: 1|2|3 = 1, lineStyle: 0|1|2|3 = 0, plotType: PlotType = 'line'): IndicatorSetting {
  return { visible, color, lineWidth, lineStyle, plotType };
}

export const DEFAULT_INDICATOR_SETTINGS: IndicatorSettings = {
  // Multi VWAP (overlay)
  'VWAP 21':  s(true,  '#35e8ff', 1, 0, 'circles'),
  'VWAP 48':  s(true,  '#f995ff', 1, 0, 'circles'),
  'VWAP 84':  s(true,  '#acff35', 1, 0, 'circles'),
  'VWAP 175': s(true,  '#5b9cf6', 1, 0, 'circles'),
  'VWAP 480': s(true,  '#ffe0b2', 1, 0, 'circles'),
  'VWAP 840': s(true,  '#f3ff00', 1, 0, 'circles'),
  // Daily VWAP
  'Daily VWAP':       s(true,  '#9598a1', 2, 0, 'circles'),
  'Prev Daily VWAP':  s(true,  '#9598a1', 2, 0, 'circles'),
  'Daily VWAP Bands': s(false, '#4caf50', 1, 2),
  // Weekly VWAP
  'Weekly VWAP':       s(true,  '#673ab7', 1, 0, 'circles'),
  'Prev Weekly VWAP':  s(true,  '#673ab7', 2, 0, 'circles'),
  'Weekly VWAP Bands': s(false, '#4caf50', 1, 2),
  // Session VWAPs
  'Session Asia':         s(true,  '#ffff00', 1, 0),
  'Session Asia Bands':   s(false, '#808080', 3, 0),
  'Session London':       s(true,  '#0000ff', 1, 0),
  'Session London Bands': s(false, '#808080', 3, 0),
  'Session NY':           s(true,  '#ff0000', 1, 0),
  'Session NY Bands':     s(false, '#808080', 3, 0),
  'Session Daily':        s(true,  '#9598a1', 1, 0),
  'Session Daily Bands':  s(true,  '#4caf50', 1, 2),
  // Sub-panes
  'Dollar Volume':  s(true, '#0000ff', 1, 0),
  'Session Volume': s(true, '#808080', 1, 0),
  'Relative QV':    s(true, '#2962ff', 1, 0),
  'ZScore':         s(true, '#ff9800', 1, 0),
  'BEFORE ITS TOO LATE': s(true, '#089981', 2, 0, 'circles'),
  'Combined Signal': s(true, '#0000ff', 2, 0),
  'Integrated Dashboard': s(true, '#9598a1', 1, 0),
  // VWMA groups
  'VWMA Auto': s(true,  '#acff35'),
  'VWMA MTF':  s(false, '#acff35'),
};

export type SubPane = 'Combined Signal' | 'BEFORE ITS TOO LATE' | 'Integrated Dashboard' | 'Dollar Volume' | 'Session Volume' | 'Relative QV' | 'ZScore';
export const DEFAULT_PANE_ORDER: SubPane[] = ['Combined Signal', 'BEFORE ITS TOO LATE', 'Dollar Volume', 'Session Volume', 'Relative QV', 'ZScore', 'Integrated Dashboard'];

interface TradingContextType {
  activeSymbol: string;
  setActiveSymbol: (s: string) => void;
  interval: Interval;
  setInterval: (i: Interval) => void;
  indicatorSettings: IndicatorSettings;
  setIndicatorSettings: (settings: IndicatorSettings) => void;
  updateIndicator: (name: string, patch: Partial<IndicatorSetting>) => void;
  resetIndicator:  (name: string) => void;
  toggleIndicator: (name: string) => void;
  paneOrder: SubPane[];
  setPaneOrder: (order: SubPane[]) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT');
  const [interval, setInterval]         = useState<Interval>('1h');
  const [paneOrder, setPaneOrder]        = useState<SubPane[]>(DEFAULT_PANE_ORDER);
  const [sidebarOpen, setSidebarOpen]    = useState(true);

  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorSettings>(() => {
    try {
      const saved = localStorage.getItem('terminal_indicator_settings_v3');
      return saved ? { ...DEFAULT_INDICATOR_SETTINGS, ...JSON.parse(saved) } : DEFAULT_INDICATOR_SETTINGS;
    } catch {
      return DEFAULT_INDICATOR_SETTINGS;
    }
  });

  useEffect(() => { wsManager.connect(); }, []);
  useEffect(() => { wsManager.subscribeToParams(activeSymbol, interval); }, [activeSymbol, interval]);
  useEffect(() => {
    localStorage.setItem('terminal_indicator_settings_v3', JSON.stringify(indicatorSettings));
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
      indicatorSettings, setIndicatorSettings, updateIndicator, resetIndicator, toggleIndicator,
      paneOrder, setPaneOrder,
      sidebarOpen, setSidebarOpen,
    }}>
      {children}
    </TradingContext.Provider>
  );
}

export function useTradingStore() {
  const ctx = useContext(TradingContext);
  if (!ctx) throw new Error('useTradingStore must be inside TradingProvider');
  return ctx;
}
