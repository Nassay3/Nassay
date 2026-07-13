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
  dailyVwap: { current: VwapLine; previous: VwapLine };
  weeklyVwap: { current: VwapLine; previous: VwapLine };
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
}

function hlc3(c: Candle): number {
  return (parseFloat(c.high) + parseFloat(c.low) + parseFloat(c.close)) / 3;
}

function hl2(c: Candle): number {
  return (parseFloat(c.high) + parseFloat(c.low)) / 2;
}

function rollingVwap(candles: Candle[], period: number): (number | null)[] {
  const values: (number | null)[] = [];
  let sumTPV = 0;
  let sumVol = 0;
  for (let i = 0; i < candles.length; i++) {
    const tp = hlc3(candles[i]);
    const vol = parseFloat(candles[i].volume);
    sumTPV += tp * vol;
    sumVol += vol;
    if (i >= period) {
      const oldTp = hlc3(candles[i - period]);
      const oldVol = parseFloat(candles[i - period].volume);
      sumTPV -= oldTp * oldVol;
      sumVol -= oldVol;
    }
    values.push(sumVol > 0 ? sumTPV / sumVol : null);
  }
  return values;
}

function sma(values: (number | null)[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v !== null) {
      sum += v;
      count++;
    }
    if (i >= period) {
      const old = values[i - period];
      if (old !== null) {
        sum -= old;
        count--;
      }
    }
    result.push(count > 0 ? sum / count : null);
  }
  return result;
}

function anchoredVwapWithBands(
  candles: Candle[],
  isNewPeriod: (current: Candle, previous: Candle | null) => boolean,
  useHl2 = false,
  stDevMultipliers: number[] = [],
): { vwap: (number | null)[]; bands: { upper: (number | null)[]; lower: (number | null)[] }[] } {
  const vwap: (number | null)[] = [];
  const bands: { upper: (number | null)[]; lower: (number | null)[] }[] = stDevMultipliers.map(() => ({ upper: [], lower: [] }));
  let sumSrcVol = 0;
  let sumVol = 0;
  let sumSrcSrcVol = 0;
  for (let i = 0; i < candles.length; i++) {
    const src = useHl2 ? hl2(candles[i]) : hlc3(candles[i]);
    const vol = parseFloat(candles[i].volume);
    if (i === 0 || isNewPeriod(candles[i], candles[i - 1])) {
      sumSrcVol = src * vol;
      sumVol = vol;
      sumSrcSrcVol = vol * src * src;
    } else {
      sumSrcVol += src * vol;
      sumVol += vol;
      sumSrcSrcVol += vol * src * src;
    }
    const v = sumVol > 0 ? sumSrcVol / sumVol : null;
    vwap.push(v);
    if (v !== null) {
      const variance = sumSrcSrcVol / sumVol - v * v;
      const stDev = Math.sqrt(Math.max(variance, 0));
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
  const d = new Date(time);
  const day = d.getUTCDay();
  const diff = (day === 0 ? -6 : 1) - day;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + diff);
}

function inSession(time: number, startHour: number, startMinute: number, endHour: number, endMinute: number): boolean {
  const d = new Date(time);
  const minutes = d.getUTCHours() * 60 + d.getUTCMinutes();
  const start = startHour * 60 + startMinute;
  const end = endHour * 60 + endMinute;
  return start <= end ? minutes >= start && minutes < end : minutes >= start || minutes < end;
}

export function calculateVwapIndicators(candles: Candle[], symbol: string, interval: string): VwapIndicators {
  const times = candles.map((c) => c.openTime);

  // Multi VWAPS Period Based
  const multiPeriods = [
    { period: 21, color: "#35e8ff" },
    { period: 48, color: "#f995ff" },
    { period: 84, color: "#acff35" },
    { period: 175, color: "#5b9cf6" },
    { period: 480, color: "#ffe0b2" },
    { period: 840, color: "#f3ff00" },
  ];
  const multiPeriodVwaps: VwapLine[] = multiPeriods.map(({ period, color }) => ({
    name: `VWAP ${period}`,
    color,
    values: times.map((t, i) => ({ time: t, value: rollingVwap(candles, period)[i] })),
  }));

  // Daily VWAP + previous close
  const daily = anchoredVwapWithBands(candles, (c, p) => !p || utcDayStart(c.openTime) !== utcDayStart(p.openTime), true);
  const dailyColoring = daily.vwap.map((v, i) => (v !== null && parseFloat(candles[i].close) > v ? "#9598a1" : "red"));
  const prevDailyClose = daily.vwap.map((v, i) => {
    if (i === 0) return null;
    const prevDayStart = utcDayStart(candles[i - 1].openTime);
    const currDayStart = utcDayStart(candles[i].openTime);
    if (currDayStart === prevDayStart) return null;
    // Find last VWAP value of previous day
    for (let j = i - 1; j >= 0; j--) {
      if (utcDayStart(candles[j].openTime) === prevDayStart) return daily.vwap[j];
      if (utcDayStart(candles[j].openTime) < prevDayStart) break;
    }
    return null;
  });
  const dailyVwap = {
    current: {
      name: "Daily VWAP",
      color: "#9598a1",
      values: times.map((t, i) => ({ time: t, value: daily.vwap[i] })),
    },
    previous: {
      name: "Prev Daily VWAP",
      color: "red",
      values: times.map((t, i) => ({ time: t, value: prevDailyClose[i] })),
    },
  };

  // Weekly VWAP + previous close
  const weekly = anchoredVwapWithBands(candles, (c, p) => !p || utcWeekStart(c.openTime) !== utcWeekStart(p.openTime), true);
  const weeklyColoring = weekly.vwap.map((v, i) => (v !== null && parseFloat(candles[i].close) > v ? "#673ab7" : "red"));
  const prevWeeklyClose = weekly.vwap.map((v, i) => {
    if (i === 0) return null;
    const prevWeekStart = utcWeekStart(candles[i - 1].openTime);
    const currWeekStart = utcWeekStart(candles[i].openTime);
    if (currWeekStart === prevWeekStart) return null;
    for (let j = i - 1; j >= 0; j--) {
      if (utcWeekStart(candles[j].openTime) === prevWeekStart) return weekly.vwap[j];
      if (utcWeekStart(candles[j].openTime) < prevWeekStart) break;
    }
    return null;
  });
  const weeklyVwap = {
    current: {
      name: "Weekly VWAP",
      color: "#673ab7",
      values: times.map((t, i) => ({ time: t, value: weekly.vwap[i] })),
    },
    previous: {
      name: "Prev Weekly VWAP",
      color: "red",
      values: times.map((t, i) => ({ time: t, value: prevWeeklyClose[i] })),
    },
  };

  // Sessions: Asia, London, NY
  const sessionDefs = [
    { name: "Asia", startH: 0, startM: 0, endH: 8, endM: 0, color: "yellow" },
    { name: "London", startH: 8, startM: 0, endH: 14, endM: 30, color: "blue" },
    { name: "NY", startH: 14, startM: 30, endH: 0, endM: 0, color: "red" },
  ];
  const sessions: VwapSession[] = sessionDefs.map((sess) => {
    const isInSession = (time: number) => inSession(time, sess.startH, sess.startM, sess.endH, sess.endM);
    const srcVol: number[] = [];
    const vol: number[] = [];
    const srcSrcVol: number[] = [];
    const vwap: (number | null)[] = [];
    const s1up: (number | null)[] = [];
    const s1dn: (number | null)[] = [];
    const s2up: (number | null)[] = [];
    const s2dn: (number | null)[] = [];
    let sumSrcVol = 0;
    let sumVol = 0;
    let sumSrcSrcVol = 0;
    for (let i = 0; i < candles.length; i++) {
      const src = hlc3(candles[i]);
      const v = parseFloat(candles[i].volume);
      const inSess = isInSession(candles[i].openTime);
      if (inSess && (i === 0 || !isInSession(candles[i - 1].openTime))) {
        sumSrcVol = src * v;
        sumVol = v;
        sumSrcSrcVol = v * src * src;
      } else if (inSess) {
        sumSrcVol += src * v;
        sumVol += v;
        sumSrcSrcVol += v * src * src;
      }
      const val = inSess && sumVol > 0 ? sumSrcVol / sumVol : null;
      vwap.push(val);
      if (val !== null) {
        const variance = sumSrcSrcVol / sumVol - val * val;
        const stDev = Math.sqrt(Math.max(variance, 0));
        s1up.push(val + stDev * 1);
        s1dn.push(val - stDev * 1);
        s2up.push(val + stDev * 2);
        s2dn.push(val - stDev * 2);
      } else {
        s1up.push(null);
        s1dn.push(null);
        s2up.push(null);
        s2dn.push(null);
      }
    }
    return {
      name: sess.name,
      vwap: { name: `${sess.name} VWAP`, color: sess.color, values: times.map((t, i) => ({ time: t, value: vwap[i] })) },
      bands: [
        { name: `${sess.name} SD+1`, upperColor: "gray", lowerColor: "gray", upper: times.map((t, i) => ({ time: t, value: s1up[i] })), lower: times.map((t, i) => ({ time: t, value: s1dn[i] })) },
        { name: `${sess.name} SD+2`, upperColor: "red", lowerColor: "blue", upper: times.map((t, i) => ({ time: t, value: s2up[i] })), lower: times.map((t, i) => ({ time: t, value: s2dn[i] })) },
      ],
    };
  });

  // Daily VWAP with bands for session view
  const dailyBands = anchoredVwapWithBands(candles, (c, p) => !p || utcDayStart(c.openTime) !== utcDayStart(p.openTime), false, [1, 2]);
  const dailySession: VwapSession = {
    name: "Daily",
    vwap: { name: "Daily VWAP", color: "gray", values: times.map((t, i) => ({ time: t, value: dailyBands.vwap[i] })) },
    bands: [
      { name: "Daily SD+1", upperColor: "gray", lowerColor: "gray", upper: times.map((t, i) => ({ time: t, value: dailyBands.bands[0].upper[i] })), lower: times.map((t, i) => ({ time: t, value: dailyBands.bands[0].lower[i] })) },
      { name: "Daily SD+2", upperColor: "red", lowerColor: "blue", upper: times.map((t, i) => ({ time: t, value: dailyBands.bands[1].upper[i] })), lower: times.map((t, i) => ({ time: t, value: dailyBands.bands[1].lower[i] })) },
    ],
  };

  // Dollar Volume per candle
  const tdv = candles.map((c) => hlc3(c) * parseFloat(c.volume));
  const tdvSma30 = sma(tdv, 30);
  const dollarVolume = {
    perCandle: { name: "Dollar Volume", color: "blue", values: times.map((t, i) => ({ time: t, value: tdv[i] })) },
    sma30: { name: "Dollar Volume SMA 30", color: "yellow", values: times.map((t, i) => ({ time: t, value: tdvSma30[i] })) },
    minimumThreshold: { name: "Min $100K", color: "white", values: times.map((t) => ({ time: t, value: 100000 })) },
    optimalThreshold: { name: "Optimal $1M", color: "blue", values: times.map((t) => ({ time: t, value: 1000000 })) },
  };

  // Session Volume Accumulated $
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
    accumulated: { name: "Session Vol Acc $", color: "gray", values: times.map((t, i) => ({ time: t, value: sessionAccum[i] })) },
    minimumThreshold: { name: "Min $10M", color: "white", values: times.map((t) => ({ time: t, value: 10000000 })) },
    optimalThreshold: { name: "Optimal $50M", color: "blue", values: times.map((t) => ({ time: t, value: 50000000 })) },
  };

  // Relative QV Dollar (R/QVOL)
  // 30 SMA of tdv, then 5-day SMA of that (1800 1-min bars). For other intervals, approximate 5-day length = 5 * 24 * 60 / intervalMinutes
  const intervalMinutes = intervalToMinutes(interval);
  const fiveDayLength = Math.max(1, Math.round((5 * 24 * 60) / intervalMinutes));
  const tdvSma30Values = sma(tdv, 30);
  const avg5Day = sma(tdvSma30Values, fiveDayLength);
  const relativeQv = tdvSma30Values.map((v, i) => (v !== null && avg5Day[i] !== null && avg5Day[i] !== 0 ? v / avg5Day[i] : null));
  const relativeQvResult = {
    relative: { name: "Relative QV Dollar", color: "blue", values: times.map((t, i) => ({ time: t, value: relativeQv[i] })) },
    minimumThreshold: { name: "Min 5.0", color: "white", values: times.map((t) => ({ time: t, value: 5 })) },
  };

  return {
    symbol,
    interval,
    multiPeriodVwaps,
    dailyVwap: {
      current: { ...dailyVwap.current, values: times.map((t, i) => ({ time: t, value: dailyVwap.current.values[i].value })) },
      previous: { ...dailyVwap.previous, values: times.map((t, i) => ({ time: t, value: dailyVwap.previous.values[i].value })) },
    },
    weeklyVwap,
    sessions: [...sessions, dailySession],
    dollarVolume,
    sessionVolumeAccumulated,
    relativeQv: relativeQvResult,
  };
}

function intervalToMinutes(interval: string): number {
  const unit = interval.slice(-1);
  const value = parseInt(interval.slice(0, -1), 10) || 1;
  switch (unit) {
    case "m":
      return value;
    case "h":
      return value * 60;
    case "d":
      return value * 24 * 60;
    case "w":
      return value * 7 * 24 * 60;
    default:
      return 60;
  }
}
