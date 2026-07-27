export interface Candle {
  openTime: number;
  closeTime: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  quoteVolume: string;
  trades: number;
  takerBuyBaseVolume: string;
  takerBuyQuoteVolume: string;
}

export interface VwapPoint {
  time: number;
  value: number | null;
  color?: string;
}

export interface VwapLine {
  name: string;
  color: string;
  values: VwapPoint[];
}

export interface VwapBand {
  name: string;
  upperColor: string;
  lowerColor: string;
  upper: VwapPoint[];
  lower: VwapPoint[];
}

export interface VwapSession {
  name: string;
  vwap: VwapLine;
  bands: VwapBand[];
}

export interface IntegratedDashboardRow {
  frame: string;
  interval: string;
  sessionVolume: number | null;
  dollarVolume: number | null;
  dollarVolumeSma: number | null;
  relativeQv: number | null;
  zVwap1: number | null;
  zVwap2: number | null;
  signal: -1 | 0 | 1 | null;
}

export interface VwapIndicators {
  symbol: string;
  interval: string;
  multiPeriodVwaps: VwapLine[];
  dailyVwap: { current: VwapLine; previous: VwapLine; bands: VwapBand[] };
  weeklyVwap: { current: VwapLine; previous: VwapLine; bands: VwapBand[] };
  sessions: VwapSession[];
  dollarVolume: {
    perCandle: VwapLine;
    sma30: VwapLine;
    minimumThreshold: VwapLine;
    optimalThreshold: VwapLine;
  };
  sessionVolumeAccumulated: {
    accumulated: VwapLine;
    minimumThreshold: VwapLine;
    optimalThreshold: VwapLine;
  };
  relativeQv: {
    relative: VwapLine;
    minimumThreshold: VwapLine;
  };
  vwapUltra1: VwapLine[];
  vwmaMtfMap: VwapLine[];
  zScore: VwapLine[];
  combinedSignal: VwapLine;
  integratedDashboard: { rows: IntegratedDashboardRow[] };
}

export type MtfCandleSources = Record<string, Candle[]>;

export const INTEGRATED_DASHBOARD_FRAMES = [
  { frame: "D", interval: "1d", periods: [48, 84] as const },
  { frame: "12H", interval: "12h", periods: [84, 480] as const },
  { frame: "6H", interval: "6h", periods: [48, 84] as const },
  { frame: "4H", interval: "4h", periods: [48, 84] as const },
  { frame: "1H", interval: "1h", periods: [48, 84] as const },
  { frame: "15M", interval: "15m", periods: [48, 84] as const },
  { frame: "1M", interval: "1m", periods: [48, 84] as const },
  { frame: "2M", interval: "2m", periods: [48, 84] as const },
  { frame: "30S", interval: "30s", periods: [48, 84] as const },
  { frame: "15S", interval: "15s", periods: [48, 84] as const },
] as const;

export function getRequiredDashboardIntervals(): string[] {
  return INTEGRATED_DASHBOARD_FRAMES.map((definition) => definition.interval);
}

export interface VwmaMtfDefinition {
  /** Display label used by the Pine plots. */
  tf: string;
  /** Binance/API interval key used to identify the supplied candle series. */
  interval: string;
  rank: number;
  periods: number[];
}

const VWMA_MTF_DEFINITIONS: VwmaMtfDefinition[] = [
  { tf: "1M",  interval: "1M",  rank: 10, periods: [48, 84, 175, 480, 840] },
  { tf: "1W",  interval: "1w",  rank: 9,  periods: [48, 84] },
  { tf: "1D",  interval: "1d",  rank: 8,  periods: [48, 175] },
  { tf: "12h", interval: "12h", rank: 7,  periods: [84, 480] },
  { tf: "6h",  interval: "6h",  rank: 6,  periods: [48, 84, 480] },
  { tf: "4h",  interval: "4h",  rank: 5,  periods: [21, 48, 84, 175, 480, 840] },
  { tf: "1h",  interval: "1h",  rank: 4,  periods: [21, 84, 175, 480, 840] },
  { tf: "45m", interval: "45m", rank: 3,  periods: [21, 84, 175, 480, 840] },
  { tf: "15m", interval: "15m", rank: 2,  periods: [21, 175, 480, 840] },
  // The Pine defaults for 2m, 1m and 30s are disabled, so they are not
  // requested until the UI exposes their per-set toggles.
];

function timeframeRank(interval: string): number {
  if (interval.endsWith("M")) return 10;
  if (interval.endsWith("w")) return 9;
  if (interval.endsWith("d")) return 8;
  const minutes = intervalToMinutes(interval);
  if (minutes >= 12 * 60) return 7;
  if (minutes >= 6 * 60) return 6;
  if (minutes >= 4 * 60) return 5;
  if (minutes >= 60) return 4;
  if (minutes >= 45) return 3;
  if (minutes >= 15) return 2;
  if (minutes >= 2) return 1;
  if (minutes >= 1) return 0;
  return -1;
}

export function getRequiredVwmaMtfDefinitions(interval: string): VwmaMtfDefinition[] {
  const currentRank = timeframeRank(interval);
  return VWMA_MTF_DEFINITIONS.filter((definition) => definition.rank > currentRank);
}

// ── helpers ──────────────────────────────────────────────────────────────────

function hlc3(c: Candle): number {
  return (parseFloat(c.high) + parseFloat(c.low) + parseFloat(c.close)) / 3;
}

function hl2(c: Candle): number {
  return (parseFloat(c.high) + parseFloat(c.low)) / 2;
}

/** Rolling VWAP over a sliding window of `period` candles */
function rollingVwap(candles: Candle[], period: number): (number | null)[] {
  const values: (number | null)[] = [];
  let sumTPV = 0;
  let sumVol = 0;
  for (let i = 0; i < candles.length; i++) {
    const tp  = hlc3(candles[i]);
    const vol = parseFloat(candles[i].volume);
    sumTPV += tp * vol;
    sumVol += vol;
    if (i >= period) {
      const oldTp  = hlc3(candles[i - period]);
      const oldVol = parseFloat(candles[i - period].volume);
      sumTPV -= oldTp * oldVol;
      sumVol -= oldVol;
    }
    // Pine's ta.sma/sum based VWAP is unavailable until the complete window
    // exists. Returning a partial-window value makes long periods (480/840)
    // look valid when the exchange history is actually insufficient.
    values.push(i >= period - 1 && sumVol > 0 ? sumTPV / sumVol : null);
  }
  return values;
}

/** Rolling simple moving average */
function sma(values: (number | null)[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v !== null) { sum += v; count++; }
    if (i >= period) {
      const old = values[i - period];
      if (old !== null) { sum -= old; count--; }
    }
    // Match Pine ta.sma semantics: emit only after `period` non-null samples.
    result.push(count === period ? sum / period : null);
  }
  return result;
}

/** Rolling standard deviation of close prices */
function rollingStdDev(candles: Candle[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  let sumSquares = 0;
  for (let i = 0; i < candles.length; i++) {
    const close = parseFloat(candles[i].close);
    sum += close;
    sumSquares += close * close;
    if (i >= period) {
      const expired = parseFloat(candles[i - period].close);
      sum -= expired;
      sumSquares -= expired * expired;
    }
    if (i < period - 1) { result.push(null); continue; }
    const mean = sum / period;
    const variance = sumSquares / period - mean * mean;
    result.push(Math.sqrt(Math.max(variance, 0)));
  }
  return result;
}

/** Pine vwapScore: rolling close VWAP, then SMA of each bar's squared deviation. */
export function calculatePineVwapZScore(candles: Candle[], period: number): (number | null)[] {
  const means = rollingVwapFromClose(candles, period);
  const squaredDeviation = candles.map((candle, index) => {
    const mean = means[index];
    return mean === null ? null : (parseFloat(candle.close) - mean) ** 2;
  });
  const variance = sma(squaredDeviation, period);
  return candles.map((candle, index) => {
    const mean = means[index];
    const value = variance[index];
    if (mean === null || value === null || value <= 0) return null;
    return (parseFloat(candle.close) - mean) / Math.sqrt(value);
  });
}

function rollingVwapFromClose(candles: Candle[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sumPriceVolume = 0;
  let sumVolume = 0;
  for (let i = 0; i < candles.length; i++) {
    const volume = parseFloat(candles[i].volume);
    sumPriceVolume += parseFloat(candles[i].close) * volume;
    sumVolume += volume;
    if (i >= period) {
      const oldVolume = parseFloat(candles[i - period].volume);
      sumPriceVolume -= parseFloat(candles[i - period].close) * oldVolume;
      sumVolume -= oldVolume;
    }
    result.push(i >= period - 1 && sumVolume > 0 ? sumPriceVolume / sumVolume : null);
  }
  return result;
}

/** Anchored VWAP that resets whenever `isNewPeriod` returns true.
 *  Returns vwap values + standard-deviation bands for each multiplier. */
function anchoredVwapWithBands(
  candles: Candle[],
  isNewPeriod: (current: Candle, previous: Candle | null) => boolean,
  useHl2 = false,
  stDevMultipliers: number[] = [],
): { vwap: (number | null)[]; bands: { upper: (number | null)[]; lower: (number | null)[] }[] } {
  const vwap: (number | null)[] = [];
  const bands: { upper: (number | null)[]; lower: (number | null)[] }[] =
    stDevMultipliers.map(() => ({ upper: [], lower: [] }));

  let sumSrcVol = 0; let sumVol = 0; let sumSrcSrcVol = 0;
  for (let i = 0; i < candles.length; i++) {
    const src = useHl2 ? hl2(candles[i]) : hlc3(candles[i]);
    const vol = parseFloat(candles[i].volume);
    if (i === 0 || isNewPeriod(candles[i], candles[i - 1])) {
      sumSrcVol = src * vol; sumVol = vol; sumSrcSrcVol = vol * src * src;
    } else {
      sumSrcVol += src * vol; sumVol += vol; sumSrcSrcVol += vol * src * src;
    }
    const v = sumVol > 0 ? sumSrcVol / sumVol : null;
    vwap.push(v);
    if (v !== null) {
      const variance = sumSrcSrcVol / sumVol - v * v;
      const stDev    = Math.sqrt(Math.max(variance, 0));
      for (let b = 0; b < stDevMultipliers.length; b++) {
        const mult = stDevMultipliers[b];
        bands[b].upper.push(v + stDev * mult);
        bands[b].lower.push(v - stDev * mult);
      }
    } else {
      for (let b = 0; b < stDevMultipliers.length; b++) {
        bands[b].upper.push(null);
        bands[b].lower.push(null);
      }
    }
  }
  return { vwap, bands };
}

function utcDayStart(time: number): number {
  const d = new Date(time);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

function utcWeekStart(time: number): number {
  const d   = new Date(time);
  const day = d.getUTCDay();
  const diff = (day === 0 ? -6 : 1) - day;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + diff);
}

function inSession(
  time: number,
  startHour: number,
  startMinute: number,
  endHour: number,
  endMinute: number,
): boolean {
  const d       = new Date(time);
  const minutes = d.getUTCHours() * 60 + d.getUTCMinutes();
  const start   = startHour * 60 + startMinute;
  const end     = endHour  * 60 + endMinute;
  return start <= end
    ? minutes >= start && minutes < end
    : minutes >= start || minutes < end;
}

function intervalToMinutes(interval: string): number {
  if (interval.endsWith("s")) return parseInt(interval) / 60;
  const unit  = interval.slice(-1);
  const value = parseInt(interval.slice(0, -1), 10) || 1;
  switch (unit) {
    case "m": return value;
    case "h": return value * 60;
    case "d": return value * 24 * 60;
    case "w": return value * 7 * 24 * 60;
    default:  return 60;
  }
}

function previousAnchoredValue(
  candles: Candle[],
  values: (number | null)[],
  periodStart: (time: number) => number,
): (number | null)[] {
  const previous: (number | null)[] = [];
  let activePeriod: number | null = null;
  let previousClose: number | null = null;
  let lastValue: number | null = null;
  for (let i = 0; i < candles.length; i++) {
    const currentPeriod = periodStart(candles[i].openTime);
    if (activePeriod !== null && currentPeriod !== activePeriod) previousClose = lastValue;
    activePeriod = currentPeriod;
    previous.push(previousClose);
    lastValue = values[i];
  }
  return previous;
}

/** Exact port of the saved Pine script "Combined VWAP Buy/Sell Signals". */
export function calculateCombinedVwapSignal(candles: Candle[], times = candles.map((c) => c.openTime)): VwapLine {
  const daily = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcDayStart(c.openTime) !== utcDayStart(p.openTime),
    false,
  ).vwap;
  const weekly = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcWeekStart(c.openTime) !== utcWeekStart(p.openTime),
    false,
  ).vwap;
  const previousDaily = previousAnchoredValue(candles, daily, utcDayStart);
  const previousWeekly = previousAnchoredValue(candles, weekly, utcWeekStart);

  const definitions = [
    { startH: 0, startM: 0, endH: 8, endM: 0 },
    { startH: 8, startM: 0, endH: 14, endM: 30 },
    { startH: 14, startM: 30, endH: 0, endM: 0 },
  ];
  const sessionSeries = definitions.map((definition) => {
    const current: (number | null)[] = [];
    const previous: (number | null)[] = [];
    const active: boolean[] = [];
    let sumPriceVolume: number | null = null;
    let sumVolume: number | null = null;
    let previousSession: number | null = null;
    for (let i = 0; i < candles.length; i++) {
      const isActive = inSession(
        candles[i].openTime,
        definition.startH,
        definition.startM,
        definition.endH,
        definition.endM,
      );
      const wasActive = i > 0 && inSession(
        candles[i - 1].openTime,
        definition.startH,
        definition.startM,
        definition.endH,
        definition.endM,
      );
      const newSession = isActive && !wasActive;
      const sourceVolume = hlc3(candles[i]) * parseFloat(candles[i].volume);
      const volume = parseFloat(candles[i].volume);
      if (newSession) {
        previousSession = i > 0 ? current[i - 1] : null;
        sumPriceVolume = sourceVolume;
        sumVolume = volume;
      } else if (sumPriceVolume !== null && sumVolume !== null) {
        // The reference Pine accumulates between starts even outside the named
        // session, then gates only the signal by the active-session boolean.
        sumPriceVolume += sourceVolume;
        sumVolume += volume;
      }
      current.push(sumVolume !== null && sumVolume > 0 ? sumPriceVolume! / sumVolume : null);
      previous.push(previousSession);
      active.push(isActive);
    }
    return { current, previous, active };
  });

  const present = (value: number | null): value is number => value !== null && Number.isFinite(value);
  const signalValues = candles.map((candle, i) => {
    const close = parseFloat(candle.close);
    const sessionGreater = sessionSeries.some((session) =>
      session.active[i] && present(session.current[i]) && present(session.previous[i]) &&
      session.current[i]! > session.previous[i]!,
    );
    const priceAboveSession = sessionSeries.some((session) =>
      session.active[i] && present(session.current[i]) && present(session.previous[i]) &&
      close > session.current[i]! && close > session.previous[i]!,
    );
    const sessionSignal = sessionGreater && priceAboveSession ? 1 : (!sessionGreater && !priceAboveSession ? -1 : 0);
    const dailyUp = present(daily[i]) && present(previousDaily[i]) && daily[i]! > previousDaily[i]!;
    const weeklyUp = present(weekly[i]) && present(previousWeekly[i]) && weekly[i]! > previousWeekly[i]!;
    const aboveDaily = present(daily[i]) && present(previousDaily[i]) && close > daily[i]! && close > previousDaily[i]!;
    const aboveWeekly = present(weekly[i]) && present(previousWeekly[i]) && close > weekly[i]! && close > previousWeekly[i]!;
    const buy = sessionSignal === 1 && dailyUp && weeklyUp && aboveDaily && aboveWeekly;
    const belowEverySession = sessionSeries.every((session) =>
      present(session.current[i]) && present(session.previous[i]) &&
      close < session.current[i]! && close < session.previous[i]!,
    );
    const sell = sessionSignal === -1 && !dailyUp && !weeklyUp &&
      present(daily[i]) && present(previousDaily[i]) && close < daily[i]! && close < previousDaily[i]! &&
      present(weekly[i]) && present(previousWeekly[i]) && close < weekly[i]! && close < previousWeekly[i]! &&
      belowEverySession;
    return buy ? 1 : sell ? -1 : 0;
  });

  return {
    name: "Combined VWAP Signal",
    color: "#0000ff",
    values: times.map((time, i) => ({ time, value: signalValues[i] })),
  };
}

export function calculateIntegratedDashboard(
  chartCandles: Candle[],
  interval: string,
  sources: MtfCandleSources,
): { rows: IntegratedDashboardRow[] } {
  let sessionVolume: number | null = null;
  for (let i = 0; i < chartCandles.length; i++) {
    const value = hlc3(chartCandles[i]) * parseFloat(chartCandles[i].volume);
    if (i === 0 || utcDayStart(chartCandles[i].openTime) !== utcDayStart(chartCandles[i - 1].openTime)) {
      sessionVolume = value;
    } else {
      sessionVolume = (sessionVolume ?? 0) + value;
    }
  }

  const rows = INTEGRATED_DASHBOARD_FRAMES.map((definition): IntegratedDashboardRow => {
    // Pine request.security evaluates against the full history of the requested
    // timeframe even when it matches the visible chart timeframe. Prefer the
    // dedicated 1,900-bar dashboard source; chartCandles is only a fallback.
    const candles = sources[definition.interval] ?? (definition.interval === interval ? chartCandles : []);
    if (!candles.length) {
      return { frame: definition.frame, interval: definition.interval, sessionVolume, dollarVolume: null, dollarVolumeSma: null, relativeQv: null, zVwap1: null, zVwap2: null, signal: null };
    }
    const dollarValues = candles.map((candle) => hlc3(candle) * parseFloat(candle.volume));
    const dollarSma = sma(dollarValues, 30);
    const relativeAverage = sma(dollarSma, 1800);
    const lastIndex = candles.length - 1;
    const dollarVolume = dollarValues[lastIndex] ?? null;
    const dollarVolumeSma = dollarSma[lastIndex] ?? null;
    const relativeQv = dollarVolumeSma !== null && relativeAverage[lastIndex] !== null && relativeAverage[lastIndex] !== 0
      ? dollarVolumeSma / relativeAverage[lastIndex]!
      : null;
    const z1 = calculatePineVwapZScore(candles, definition.periods[0])[lastIndex] ?? null;
    const z2 = calculatePineVwapZScore(candles, definition.periods[1])[lastIndex] ?? null;
    const complete = [sessionVolume, dollarVolume, dollarVolumeSma, relativeQv, z1, z2].every(
      (value) => value !== null && Number.isFinite(value),
    );
    let signal: -1 | 0 | 1 | null = null;
    if (complete) {
      const volumeInRange = sessionVolume! > 8e6 && sessionVolume! < 50e6;
      const dollarInRange = dollarVolume! > 1e5 && dollarVolume! < 1e6;
      const averageInRange = dollarVolumeSma! > 1e5 && dollarVolumeSma! < 1e6;
      const buy = volumeInRange && dollarInRange && averageInRange && relativeQv! > 2 && z1! > -0.875 && z2! > -0.875;
      const sell = volumeInRange && dollarInRange && averageInRange && relativeQv! > 2 && z1! < 0.875 && z2! < 0.875;
      signal = buy ? 1 : sell ? -1 : 0;
    }
    return { frame: definition.frame, interval: definition.interval, sessionVolume, dollarVolume, dollarVolumeSma, relativeQv, zVwap1: z1, zVwap2: z2, signal };
  });
  return { rows };
}

/** Shared band builder: turns raw band arrays into VwapBand objects */
function buildBands(
  times: number[],
  rawBands: { upper: (number | null)[]; lower: (number | null)[] }[],
  defs: { name: string; upperColor: string; lowerColor: string }[],
): VwapBand[] {
  return rawBands.map((rb, i) => ({
    name:       defs[i]?.name        ?? `Band ±${i + 1}σ`,
    upperColor: defs[i]?.upperColor  ?? "#4caf50",
    lowerColor: defs[i]?.lowerColor  ?? "#f44336",
    upper:      times.map((t, j) => ({ time: t, value: rb.upper[j] })),
    lower:      times.map((t, j) => ({ time: t, value: rb.lower[j] })),
  }));
}

// ── Color palette — shared between Multi VWAP and VWMA (matched by period) ───

export const PERIOD_COLORS: Record<number, string> = {
  21:  "#35e8ff",  // cyan
  48:  "#f995ff",  // pink
  84:  "#acff35",  // lime
  175: "#5b9cf6",  // blue
  480: "#ffe0b2",  // peach
  840: "#f3ff00",  // yellow
};

const BAND_DEFS = [
  { name: "Band ±1σ", upperColor: "#4caf50", lowerColor: "#4caf50" },
  { name: "Band ±2σ", upperColor: "#f44336", lowerColor: "#f44336" },
];

// ── Main export ───────────────────────────────────────────────────────────────

export function calculateVwapIndicators(
  candles: Candle[],
  symbol: string,
  interval: string,
  mtfSources: MtfCandleSources = {},
): VwapIndicators {
  const times = candles.map((c) => c.openTime);

  // ── Multi VWAP (rolling, period-based) ─────────────────────────────────────
  const multiPeriods = [
    { period: 21,  color: PERIOD_COLORS[21]  },
    { period: 48,  color: PERIOD_COLORS[48]  },
    { period: 84,  color: PERIOD_COLORS[84]  },
    { period: 175, color: PERIOD_COLORS[175] },
    { period: 480, color: PERIOD_COLORS[480] },
    { period: 840, color: PERIOD_COLORS[840] },
  ];
  const multiPeriodVwaps: VwapLine[] = multiPeriods.map(({ period, color }) => {
    const vals = rollingVwap(candles, period);
    return {
      name:   `VWAP ${period}`,
      color,
      values: times.map((t, i) => ({ time: t, value: vals[i] })),
    };
  });

  // ── Daily VWAP with bands ──────────────────────────────────────────────────
  const daily     = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcDayStart(c.openTime) !== utcDayStart(p!.openTime),
    true, [1, 2],
  );
  const prevDailyVwap: (number | null)[] = [];
  let activeDay: number | null = null;
  let previousDayClose: number | null = null;
  let lastDailyValue: number | null = null;
  for (let i = 0; i < candles.length; i++) {
    const currDay = utcDayStart(candles[i].openTime);
    if (activeDay !== null && currDay !== activeDay) {
      previousDayClose = lastDailyValue;
    }
    activeDay = currDay;
    prevDailyVwap.push(previousDayClose);
    lastDailyValue = daily.vwap[i];
  }
  const dailyVwap = {
    current:  { name: "Daily VWAP",      color: "#9598a1", values: times.map((t, i) => ({ time: t, value: daily.vwap[i], color: daily.vwap[i] !== null && parseFloat(candles[i].close) > daily.vwap[i]! ? "#9598a1" : "#ff0000" })) },
    previous: { name: "Prev Daily VWAP", color: "#9598a1", values: times.map((t, i) => ({ time: t, value: prevDailyVwap[i], color: prevDailyVwap[i] !== null && parseFloat(candles[i].close) > prevDailyVwap[i]! ? "#9598a1" : "#ff0000" })) },
    bands:    buildBands(times, daily.bands, BAND_DEFS),
  };

  // ── Weekly VWAP with bands ─────────────────────────────────────────────────
  const weekly    = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcWeekStart(c.openTime) !== utcWeekStart(p!.openTime),
    true, [1, 2],
  );
  const prevWeeklyVwap: (number | null)[] = [];
  let activeWeek: number | null = null;
  let previousWeekClose: number | null = null;
  let lastWeeklyValue: number | null = null;
  for (let i = 0; i < candles.length; i++) {
    const currWeek = utcWeekStart(candles[i].openTime);
    if (activeWeek !== null && currWeek !== activeWeek) {
      previousWeekClose = lastWeeklyValue;
    }
    activeWeek = currWeek;
    prevWeeklyVwap.push(previousWeekClose);
    lastWeeklyValue = weekly.vwap[i];
  }
  const weeklyVwap = {
    current:  { name: "Weekly VWAP",      color: "#673ab7", values: times.map((t, i) => ({ time: t, value: weekly.vwap[i], color: weekly.vwap[i] !== null && parseFloat(candles[i].close) > weekly.vwap[i]! ? "#673ab7" : "#ff0000" })) },
    previous: { name: "Prev Weekly VWAP", color: "#673ab7", values: times.map((t, i) => ({ time: t, value: prevWeeklyVwap[i], color: prevWeeklyVwap[i] !== null && parseFloat(candles[i].close) > prevWeeklyVwap[i]! ? "#673ab7" : "#ff0000" })) },
    bands:    buildBands(times, weekly.bands, BAND_DEFS),
  };

  // ── Session VWAPs — Asia / London / NY — all with bands ───────────────────
  const sessionDefs = [
    { name: "Asia",   startH: 0,  startM: 0,  endH: 8,  endM: 0,  color: "#ffff00" },
    { name: "London", startH: 8,  startM: 0,  endH: 14, endM: 30, color: "#0000ff" },
    { name: "NY",     startH: 14, startM: 30, endH: 0,  endM: 0,  color: "#ff0000" },
  ];

  const sessions: VwapSession[] = sessionDefs.map((sess) => {
    const isIn = (t: number) =>
      inSession(t, sess.startH, sess.startM, sess.endH, sess.endM);

    const vwapArr:          (number | null)[] = [];
    const upperBand1:       (number | null)[] = [];
    const lowerBand1:       (number | null)[] = [];
    const upperBand2:       (number | null)[] = [];
    const lowerBand2:       (number | null)[] = [];

    let sumSV = 0, sumV = 0, sumSSV = 0;

    for (let i = 0; i < candles.length; i++) {
      const src  = hlc3(candles[i]);
      const v    = parseFloat(candles[i].volume);
      const inS  = isIn(candles[i].openTime);
      const newS = inS && (i === 0 || !isIn(candles[i - 1].openTime));

      if (newS) {
        sumSV = src * v; sumV = v; sumSSV = v * src * src;
      } else if (inS) {
        sumSV += src * v; sumV += v; sumSSV += v * src * src;
      }

      if (inS && sumV > 0) {
        const vwap_    = sumSV / sumV;
        const variance = sumSSV / sumV - vwap_ * vwap_;
        const stDev    = Math.sqrt(Math.max(variance, 0));
        vwapArr.push(vwap_);
        upperBand1.push(vwap_ + stDev * 1);
        lowerBand1.push(vwap_ - stDev * 1);
        upperBand2.push(vwap_ + stDev * 2);
        lowerBand2.push(vwap_ - stDev * 2);
      } else {
        vwapArr.push(null);
        upperBand1.push(null); lowerBand1.push(null);
        upperBand2.push(null); lowerBand2.push(null);
      }
    }

    return {
      name: sess.name,
      vwap: { name: `Session ${sess.name}`, color: sess.color, values: times.map((t, i) => ({ time: t, value: vwapArr[i] })) },
      bands: [
        {
          name: `Session ${sess.name} Band ±1σ`, upperColor: "rgba(128,128,128,0.30)", lowerColor: "rgba(128,128,128,0.30)",
          upper: times.map((t, i) => ({ time: t, value: upperBand1[i] })),
          lower: times.map((t, i) => ({ time: t, value: lowerBand1[i] })),
        },
        {
          name: `Session ${sess.name} Band ±2σ`, upperColor: "rgba(255,0,0,0.20)", lowerColor: "rgba(0,0,255,0.20)",
          upper: times.map((t, i) => ({ time: t, value: upperBand2[i] })),
          lower: times.map((t, i) => ({ time: t, value: lowerBand2[i] })),
        },
      ],
    };
  });

  // Daily VWAP in "session" slot (HLC3-anchored, with ±1σ ±2σ) — index 3
  const dailyBands = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcDayStart(c.openTime) !== utcDayStart(p!.openTime),
    false, [1, 2],
  );
  sessions.push({
    name: "Daily",
    vwap: {
      name: "Session Daily", color: "#9598a1",
      values: times.map((t, i) => ({ time: t, value: dailyBands.vwap[i] })),
    },
    bands: buildBands(times, dailyBands.bands, BAND_DEFS),
  });

  // ── Dollar Volume per candle ────────────────────────────────────────────────
  const tdv      = candles.map((c) => hlc3(c) * parseFloat(c.volume));
  const tdvSma30 = sma(tdv, 30);
  const dollarVolume = {
    perCandle:        { name: "Dollar Volume", color: "#0000ff", values: times.map((t, i) => ({ time: t, value: tdv[i], color: parseFloat(candles[i].close) < parseFloat(candles[i].open) ? "#808080" : "#0000ff" })) },
    sma30:            { name: "DV SMA 30",     color: "#ffff00", values: times.map((t, i) => ({ time: t, value: tdvSma30[i] })) },
    minimumThreshold: { name: "Min $100K",     color: "#ffffff", values: times.map((t) => ({ time: t, value: 100_000 })) },
    optimalThreshold: { name: "Optimal $1M",   color: "#0000ff", values: times.map((t) => ({ time: t, value: 1_000_000 })) },
  };

  // ── Session Volume Accumulated $ ───────────────────────────────────────────
  const sessionAccum: (number | null)[] = [];
  let acc = 0;
  for (let i = 0; i < candles.length; i++) {
    if (i === 0 || utcDayStart(candles[i].openTime) !== utcDayStart(candles[i - 1].openTime)) {
      acc = hlc3(candles[i]) * parseFloat(candles[i].volume);
    } else {
      acc += hlc3(candles[i]) * parseFloat(candles[i].volume);
    }
    sessionAccum.push(acc);
  }
  const sessionVolumeAccumulated = {
    accumulated:      { name: "Session Vol Acc $", color: "#808080", values: times.map((t, i) => ({ time: t, value: sessionAccum[i] })) },
    minimumThreshold: { name: "Min $10M",          color: "#ffffff", values: times.map((t) => ({ time: t, value: 10_000_000 })) },
    optimalThreshold: { name: "Optimal $50M",      color: "#0000ff", values: times.map((t) => ({ time: t, value: 50_000_000 })) },
  };

  // ── Relative QV Dollar (R/QVOL) ───────────────────────────────────────────
  // The reference Pine script uses a fixed 1,800-bar window on every chart
  // timeframe (despite the legacy "5 days / based on 1min" comment).
  const fiveDayLength   = 1800;
  const tdvSma30v       = sma(tdv, 30);
  const avg5Day         = sma(tdvSma30v, fiveDayLength);
  const relQv           = tdvSma30v.map((v, i) =>
    v !== null && avg5Day[i] !== null && avg5Day[i] !== 0 ? v / avg5Day[i]! : null,
  );
  const relativeQv = {
    relative:         { name: "Relative QV Dollar", color: "#2962ff", values: times.map((t, i) => ({ time: t, value: relQv[i] })) },
    minimumThreshold: { name: "Min 5.0",            color: "#ffffff", values: times.map((t) => ({ time: t, value: 5 })) },
  };

  // ── VWAP ULTRA1 (VWMA auto-select by timeframe) ───────────────────────────
  const vwapUltra1 = calculateVwmaForInterval(candles, interval, times);

  // ── VWMA MTF Map (higher-TF approximation) ────────────────────────────────
  const vwmaMtfMap = calculateVwmaMtfMap(candles, interval, times, mtfSources);

  // ── Z-Score (periods 48 & 84) ────────────────────────────────────────────
  const zScore = calculateZScore(candles, times, [48, 84]);
  const combinedSignal = calculateCombinedVwapSignal(candles, times);
  const integratedDashboard = calculateIntegratedDashboard(candles, interval, mtfSources);

  return {
    symbol, interval,
    multiPeriodVwaps,
    dailyVwap,
    weeklyVwap,
    sessions,
    dollarVolume,
    sessionVolumeAccumulated,
    relativeQv,
    vwapUltra1,
    vwmaMtfMap,
    zScore,
    combinedSignal,
    integratedDashboard,
  };
}

/** Keep only points at or after minTime while preserving the indicator shape. */
export function trimVwapIndicators(
  indicators: VwapIndicators,
  minTime: number,
): VwapIndicators {
  const trim = (value: unknown): unknown => {
    if (Array.isArray(value)) {
      const first = value[0] as Record<string, unknown> | undefined;
      if (first && typeof first === "object" && "time" in first && "value" in first) {
        const start = value.findIndex((point) => (point as VwapPoint).time >= minTime);
        return start < 0 ? [] : value.slice(start);
      }
      return value.map(trim);
    }
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, child]) => [key, trim(child)]),
      );
    }
    return value;
  };
  return trim(indicators) as VwapIndicators;
}

// ── VWMA auto per timeframe ───────────────────────────────────────────────────

function calculateVwmaForInterval(candles: Candle[], interval: string, times: number[]): VwapLine[] {
  const periodMap: Record<string, number[]> = {
    "3M":  [48, 84],
    "1M":  [48, 84],
    "1w":  [48, 84],
    "1d":  [48, 175],
    "12h": [84, 480],
    "6h":  [48, 84, 480],
    "4h":  [21, 48, 84, 175, 480, 840],
    "2h":  [21, 84, 175, 480, 840],
    "1h":  [21, 84, 175, 480, 840],
    "45m": [21, 84, 175, 480, 840],
    "30m": [21, 175, 480, 840],
    "15m": [21, 175, 480, 840],
    "5m":  [84, 175],
    "3m":  [84, 175],
    "2m":  [84, 175],
    "1m":  [84, 175],
    "30s": [21, 48],
    "15s": [21, 48],
    "5s":  [175],
  };

  const periods = periodMap[interval] ?? [84, 175];

  return periods.map((period) => {
    const vals = rollingVwap(candles, period);
    return {
      name:   `VWMA ${period}`,
      color:  PERIOD_COLORS[period] ?? "#ffffff",
      values: times.map((t, i) => ({ time: t, value: vals[i] })),
    };
  });
}

// ── VWMA MTF Map ─────────────────────────────────────────────────────────────

export function calculateVwmaMtfMap(
  candles: Candle[],
  interval: string,
  times: number[],
  mtfSources: MtfCandleSources,
): VwapLine[] {
  const lines: VwapLine[] = [];

  for (const def of getRequiredVwmaMtfDefinitions(interval)) {
    const higherCandles = mtfSources[def.interval] ?? [];
    if (!higherCandles.length) continue;

    for (const period of def.periods) {
      const higherValues = rollingVwap(higherCandles, period);
      let completedHigherIndex = -1;
      let activeHigherIndex = 0;
      const mappedValues: (number | null)[] = [];

      for (let i = 0; i < candles.length; i++) {
        const current = candles[i];
        while (
          completedHigherIndex + 1 < higherCandles.length &&
          higherCandles[completedHigherIndex + 1].closeTime <= current.closeTime
        ) {
          completedHigherIndex++;
        }
        while (
          activeHigherIndex + 1 < higherCandles.length &&
          higherCandles[activeHigherIndex + 1].openTime <= current.openTime
        ) {
          activeHigherIndex++;
        }

        // barmerge.lookahead_off exposes a historical higher-timeframe value
        // only on the lower bar that closes that higher candle. The final live
        // lower bar may use the developing higher candle, matching TradingView.
        const isRealtimeTail = i === candles.length - 1 &&
          higherCandles[activeHigherIndex]?.openTime <= current.openTime &&
          higherCandles[activeHigherIndex]?.closeTime >= current.closeTime;
        const sourceIndex = isRealtimeTail ? activeHigherIndex : completedHigherIndex;
        mappedValues.push(sourceIndex >= 0 ? higherValues[sourceIndex] ?? null : null);
      }

      lines.push({
        name:   `VWMA ${period} [${def.tf}]`,
        color:  PERIOD_COLORS[period] ?? "#ffffff",
        values: times.map((t, i) => ({ time: t, value: mappedValues[i] })),
      });
    }
  }
  return lines;
}

// ── ZScore ────────────────────────────────────────────────────────────────────

function calculateZScore(candles: Candle[], times: number[], periods: number[]): VwapLine[] {
  const closes  = candles.map((c) => parseFloat(c.close));
  const zColors = ["#ff9800", "#e91e63"];

  return periods.map((period, idx) => {
    const vwmaVals = rollingVwap(candles, period);
    const stdVals  = rollingStdDev(candles, period);
    const values   = closes.map((cl, i) => {
      const v = vwmaVals[i];
      const s = stdVals[i];
      return v !== null && s !== null && s > 0 ? (cl - v) / s : null;
    });
    return {
      name:   `ZScore ${period}`,
      color:  zColors[idx] ?? "#ffffff",
      values: times.map((t, i) => ({ time: t, value: values[i] })),
    };
  });
}
