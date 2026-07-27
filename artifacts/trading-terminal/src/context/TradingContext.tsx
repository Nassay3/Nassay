import React, { createContext, useContext, useState, useEffect } from 'react';
import { wsManager } from '@/lib/ws';

export type Interval = '5s' | '15s' | '30s' | '1m' | '2m' | '5m' | '15m' | '30m' | '45m' | '1h' | '4h' | '6h' | '12h' | '1d' | '1w' | '1M' | '3M';
export type CandleStyle = 'candles' | 'hollow' | 'heikin-ashi';
export type MarketType = 'spot' | 'futures';

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
export const ALL_INTERVALS = Object.keys(INTERVAL_LABELS) as Interval[];

// Timeframe visibility rules for overlay VWAPs
export const INTERVAL_VISIBILITY: Record<string, Interval[]> = {
  'Daily VWAP':       ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Prev Daily VWAP':  ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Weekly VWAP':      ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
  'Prev Weekly VWAP': ['5s', '15s', '30s', '1m', '2m', '5m', '15m', '30m', '45m', '1h', '4h', '6h', '12h', '1d', '1w', '1M', '3M'],
};

export function isVisibleForInterval(
  key: string,
  interval: Interval,
  setting?: { visibleIntervals?: Interval[] },
): boolean {
  if (setting?.visibleIntervals) return setting.visibleIntervals.includes(interval);
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
  opacity?: number;
  showLastValue?: boolean;
  showPriceLine?: boolean;
  visibleIntervals?: Interval[];
}

export interface IndicatorSettings {
  [key: string]: IndicatorSetting;
}

function s(visible: boolean, color: string, lineWidth: 1|2|3 = 1, lineStyle: 0|1|2|3 = 0, plotType: PlotType = 'line'): IndicatorSetting {
  return { visible, color, lineWidth, lineStyle, plotType, opacity: 100, showLastValue: false, showPriceLine: false };
}

function paneSetting(visible: boolean, color: string, lineWidth: 1|2|3 = 1, lineStyle: 0|1|2|3 = 0, plotType: PlotType = 'line'): IndicatorSetting {
  return { ...s(visible, color, lineWidth, lineStyle, plotType), showLastValue: true };
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
  'Session VWAP':         s(true,  '#9598a1', 1, 0),
  'Session Asia':         s(true,  '#ffff00', 1, 0),
  'Session Asia Bands':   s(false, '#808080', 3, 0),
  'Session London':       s(true,  '#0000ff', 1, 0),
  'Session London Bands': s(false, '#808080', 3, 0),
  'Session NY':           s(true,  '#ff0000', 1, 0),
  'Session NY Bands':     s(false, '#808080', 3, 0),
  'Session Daily':        s(true,  '#9598a1', 1, 0),
  'Session Daily Bands':  s(true,  '#4caf50', 1, 2),
  // Sub-panes
  'Dollar Volume':  paneSetting(true, '#0000ff', 1, 0),
  'Session Volume': paneSetting(false, '#808080', 1, 0),
  'Relative QV':    paneSetting(false, '#2962ff', 1, 0),
  'ZScore':         paneSetting(false, '#ff9800', 1, 0),
  'ZScore 48':      paneSetting(true, '#ff9800', 2, 0),
  'ZScore 84':      paneSetting(true, '#e91e63', 2, 0),
  'ZScore Level -2': s(true, '#f6465d', 1, 2),
  'ZScore Level -1': s(true, '#f6465d', 1, 2),
  'ZScore Level 0':  s(true, '#6b7280', 1, 2),
  'ZScore Level 1':  s(true, '#0ecb81', 1, 2),
  'ZScore Level 2':  s(true, '#0ecb81', 1, 2),
  'Combined Signal': paneSetting(true, '#0000ff', 2, 0),
  'Integrated Dashboard': paneSetting(false, '#9598a1', 1, 0),
  // VWMA groups
  'VWMA Auto': s(true,  '#acff35'),
  'VWMA MTF':  s(false, '#acff35'),
};

export type SubPane = 'Combined Signal' | 'Integrated Dashboard' | 'Dollar Volume' | 'Session Volume' | 'Relative QV' | 'ZScore';
export const DEFAULT_PANE_ORDER: SubPane[] = ['Combined Signal', 'Dollar Volume', 'Session Volume', 'Relative QV', 'ZScore', 'Integrated Dashboard'];

const MAIN_OVERLAY_KEYS = [
  'VWAP 21', 'VWAP 48', 'VWAP 84', 'VWAP 175', 'VWAP 480', 'VWAP 840',
  'Daily VWAP', 'Prev Daily VWAP', 'Daily VWAP Bands',
  'Weekly VWAP', 'Prev Weekly VWAP', 'Weekly VWAP Bands',
  'Session Asia', 'Session Asia Bands', 'Session London', 'Session London Bands',
  'Session NY', 'Session NY Bands', 'Session Daily', 'Session Daily Bands',
  'VWMA Auto', 'VWMA MTF',
] as const;

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable in private or policy-restricted browser contexts.
  }
}

function storedSymbol(): string {
  const saved = storageGet('terminal_active_symbol_v1');
  return saved && /^[A-Z0-9]{4,20}$/.test(saved) ? saved : 'BTCUSDT';
}

function storedInterval(): Interval {
  const saved = storageGet('terminal_interval_v1');
  return saved && saved in INTERVAL_LABELS ? saved as Interval : '1h';
}

function storedCandleStyle(): CandleStyle {
  const saved = storageGet('terminal_candle_style_v1');
  return saved === 'hollow' || saved === 'heikin-ashi' || saved === 'candles'
    ? saved
    : 'candles';
}

function storedMarketType(): MarketType {
  return storageGet('terminal_market_type_v1') === 'futures' ? 'futures' : 'spot';
}

interface TradingContextType {
  activeSymbol: string;
  setActiveSymbol: (s: string) => void;
  interval: Interval;
  setInterval: (i: Interval) => void;
  candleStyle: CandleStyle;
  setCandleStyle: (style: CandleStyle) => void;
  marketType: MarketType;
  setMarketType: (market: MarketType) => void;
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
  const [activeSymbol, setActiveSymbol] = useState(storedSymbol);
  const [interval, setInterval]         = useState<Interval>(storedInterval);
  const [candleStyle, setCandleStyle]   = useState<CandleStyle>(storedCandleStyle);
  const [marketType, setMarketType]     = useState<MarketType>(storedMarketType);
  const [paneOrder, setPaneOrder] = useState<SubPane[]>(() => {
    try {
      const saved = JSON.parse(storageGet('terminal_pane_order_v1') ?? 'null');
      if (Array.isArray(saved) && saved.length === DEFAULT_PANE_ORDER.length && saved.every((pane): pane is SubPane => DEFAULT_PANE_ORDER.includes(pane))) {
        return saved;
      }
    } catch {
      // Keep the professional default layout when saved data is invalid.
    }
    return DEFAULT_PANE_ORDER;
  });
  const [sidebarOpen, setSidebarOpen] = useState(
    () => storageGet('terminal_indicator_sidebar_v1') !== 'closed',
  );

  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorSettings>(() => {
    try {
      const current = storageGet('terminal_indicator_settings_v5');
      if (current) return { ...DEFAULT_INDICATOR_SETTINGS, ...JSON.parse(current) };
      const legacy = storageGet('terminal_indicator_settings_v4')
        ?? storageGet('terminal_indicator_settings_v3');
      if (!legacy) return DEFAULT_INDICATOR_SETTINGS;
      const migrated = { ...DEFAULT_INDICATOR_SETTINGS, ...JSON.parse(legacy) };
      for (const key of MAIN_OVERLAY_KEYS) {
        migrated[key] = { ...migrated[key], showLastValue: false };
      }
      delete migrated['BEFORE ITS TOO LATE'];
      return migrated;
    } catch {
      return DEFAULT_INDICATOR_SETTINGS;
    }
  });

  useEffect(() => { wsManager.connect(); }, []);
  useEffect(() => { wsManager.subscribeToParams(activeSymbol, interval, marketType); }, [activeSymbol, interval, marketType]);
  useEffect(() => {
    storageSet('terminal_active_symbol_v1', activeSymbol);
  }, [activeSymbol]);
  useEffect(() => {
    storageSet('terminal_interval_v1', interval);
  }, [interval]);
  useEffect(() => {
    storageSet('terminal_candle_style_v1', candleStyle);
  }, [candleStyle]);
  useEffect(() => {
    storageSet('terminal_market_type_v1', marketType);
    if (marketType === 'futures' && interval.endsWith('s')) setInterval('1m');
  }, [marketType, interval]);
  useEffect(() => {
    storageSet('terminal_indicator_sidebar_v1', sidebarOpen ? 'open' : 'closed');
  }, [sidebarOpen]);
  useEffect(() => {
    storageSet('terminal_indicator_settings_v5', JSON.stringify(indicatorSettings));
  }, [indicatorSettings]);
  useEffect(() => {
    storageSet('terminal_pane_order_v1', JSON.stringify(paneOrder));
  }, [paneOrder]);

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
      candleStyle, setCandleStyle,
      marketType, setMarketType,
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
