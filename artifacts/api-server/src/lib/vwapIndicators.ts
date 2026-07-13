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
    values.push(sumVol > 0 ? sumTPV / sumVol : null);
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
    result.push(count > 0 ? sum / count : null);
  }
  return result;
}

/** Rolling standard deviation of close prices */
function rollingStdDev(candles: Candle[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) { result.push(null); continue; }
    let sumX = 0; let sumX2 = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const c = parseFloat(candles[j].close);
      sumX += c; sumX2 += c * c;
    }
    const mean     = sumX / period;
    const variance = sumX2 / period - mean * mean;
    result.push(Math.sqrt(Math.max(variance, 0)));
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
  for (let i = 0; i < candles.length; i++) {
    const currDay = utcDayStart(candles[i].openTime);
    let prevVal: number | null = null;
    for (let j = i - 1; j >= 0; j--) {
      if (utcDayStart(candles[j].openTime) < currDay) { prevVal = daily.vwap[j]; break; }
    }
    prevDailyVwap.push(prevVal);
  }
  const dailyVwap = {
    current:  { name: "Daily VWAP",      color: "#9598a1", values: times.map((t, i) => ({ time: t, value: daily.vwap[i] })) },
    previous: { name: "Prev Daily VWAP", color: "#e91e63", values: times.map((t, i) => ({ time: t, value: prevDailyVwap[i] })) },
    bands:    buildBands(times, daily.bands, BAND_DEFS),
  };

  // ── Weekly VWAP with bands ─────────────────────────────────────────────────
  const weekly    = anchoredVwapWithBands(
    candles,
    (c, p) => !p || utcWeekStart(c.openTime) !== utcWeekStart(p!.openTime),
    true, [1, 2],
  );
  const prevWeeklyVwap: (number | null)[] = [];
  for (let i = 0; i < candles.length; i++) {
    const currWeek = utcWeekStart(candles[i].openTime);
    let prevVal: number | null = null;
    for (let j = i - 1; j >= 0; j--) {
      if (utcWeekStart(candles[j].openTime) < currWeek) { prevVal = weekly.vwap[j]; break; }
    }
    prevWeeklyVwap.push(prevVal);
  }
  const weeklyVwap = {
    current:  { name: "Weekly VWAP",      color: "#673ab7", values: times.map((t, i) => ({ time: t, value: weekly.vwap[i] })) },
    previous: { name: "Prev Weekly VWAP", color: "#ff5252", values: times.map((t, i) => ({ time: t, value: prevWeeklyVwap[i] })) },
    bands:    buildBands(times, weekly.bands, BAND_DEFS),
  };

  // ── Session VWAPs — Asia / London / NY — all with bands ───────────────────
  const sessionDefs = [
    { name: "Asia",   startH: 0,  startM: 0,  endH: 8,  endM: 0,  color: "#f9a825" },
    { name: "London", startH: 8,  startM: 0,  endH: 14, endM: 30, color: "#9c27b0" },
    { name: "NY",     startH: 14, startM: 30, endH: 0,  endM: 0,  color: "#00e5ff" },
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
          name: `Session ${sess.name} Band ±1σ`, upperColor: "#4caf50", lowerColor: "#4caf50",
          upper: times.map((t, i) => ({ time: t, value: upperBand1[i] })),
          lower: times.map((t, i) => ({ time: t, value: lowerBand1[i] })),
        },
        {
          name: `Session ${sess.name} Band ±2σ`, upperColor: "#f44336", lowerColor: "#f44336",
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
    perCandle:        { name: "Dollar Volume", color: "#2196f3", values: times.map((t, i) => ({ time: t, value: tdv[i] })) },
    sma30:            { name: "DV SMA 30",     color: "#ffeb3b", values: times.map((t, i) => ({ time: t, value: tdvSma30[i] })) },
    minimumThreshold: { name: "Min $100K",     color: "#555555", values: times.map((t) => ({ time: t, value: 100_000 })) },
    optimalThreshold: { name: "Optimal $1M",   color: "#2196f3", values: times.map((t) => ({ time: t, value: 1_000_000 })) },
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
    accumulated:      { name: "Session Vol Acc $", color: "#9e9e9e", values: times.map((t, i) => ({ time: t, value: sessionAccum[i] })) },
    minimumThreshold: { name: "Min $10M",          color: "#555555", values: times.map((t) => ({ time: t, value: 10_000_000 })) },
    optimalThreshold: { name: "Optimal $50M",      color: "#2196f3", values: times.map((t) => ({ time: t, value: 50_000_000 })) },
  };

  // ── Relative QV Dollar (R/QVOL) ───────────────────────────────────────────
  const intervalMinutes = intervalToMinutes(interval);
  const fiveDayLength   = Math.max(1, Math.round(1800 / intervalMinutes));
  const tdvSma30v       = sma(tdv, 30);
  const avg5Day         = sma(tdvSma30v, fiveDayLength);
  const relQv           = tdvSma30v.map((v, i) =>
    v !== null && avg5Day[i] !== null && avg5Day[i] !== 0 ? v / avg5Day[i]! : null,
  );
  const relativeQv = {
    relative:         { name: "Relative QV Dollar", color: "#ff9800", values: times.map((t, i) => ({ time: t, value: relQv[i] })) },
    minimumThreshold: { name: "Min 5.0",            color: "#555555", values: times.map((t) => ({ time: t, value: 5 })) },
  };

  // ── VWAP ULTRA1 (VWMA auto-select by timeframe) ───────────────────────────
  const vwapUltra1 = calculateVwmaForInterval(candles, interval, times);

  // ── VWMA MTF Map (higher-TF approximation) ────────────────────────────────
  const vwmaMtfMap = calculateVwmaMtfMap(candles, interval, times);

  // ── Z-Score (periods 48 & 84) ────────────────────────────────────────────
  const zScore = calculateZScore(candles, times, [48, 84]);

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
  };
}

// ── VWMA auto per timeframe ───────────────────────────────────────────────────

function calculateVwmaForInterval(candles: Candle[], interval: string, times: number[]): VwapLine[] {
  const periodMap: Record<string, number[]> = {
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
    "1m":  [84, 175],
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

function calculateVwmaMtfMap(candles: Candle[], interval: string, times: number[]): VwapLine[] {
  const tfDefs: { tf: string; minutes: number; periods: number[] }[] = [
    { tf: "1W",  minutes: 7 * 24 * 60,  periods: [48, 84] },
    { tf: "1D",  minutes: 24 * 60,       periods: [48, 175] },
    { tf: "12h", minutes: 12 * 60,       periods: [84, 480] },
    { tf: "6h",  minutes: 6 * 60,        periods: [48, 84, 480] },
    { tf: "4h",  minutes: 4 * 60,        periods: [21, 48, 84, 175, 480, 840] },
    { tf: "1h",  minutes: 60,            periods: [21, 84, 175, 480, 840] },
    { tf: "45m", minutes: 45,            periods: [21, 84, 175, 480, 840] },
    { tf: "15m", minutes: 15,            periods: [21, 175, 480, 840] },
    { tf: "5m",  minutes: 5,             periods: [84, 175] },
    { tf: "1m",  minutes: 1,             periods: [84, 175] },
  ];

  const curMin = intervalToMinutes(interval);
  const lines: VwapLine[] = [];

  for (const def of tfDefs) {
    if (def.minutes <= curMin) continue;
    const ratio = def.minutes / curMin;
    for (const period of def.periods) {
      const eff = Math.round(period * ratio);
      if (eff <= 0 || eff > candles.length) continue;
      const vals = rollingVwap(candles, eff);
      lines.push({
        name:   `VWMA ${period} [${def.tf}]`,
        color:  PERIOD_COLORS[period] ?? "#ffffff",
        values: times.map((t, i) => ({ time: t, value: vals[i] })),
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
