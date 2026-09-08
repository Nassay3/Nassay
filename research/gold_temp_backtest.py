from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

DATA_URL = "https://raw.githubusercontent.com/simom1/XAUUSD-history/main/Gold-Cash/XAUUSD/XAUUSD_M5.csv"
TEST_START = pd.Timestamp("2021-09-08", tz="UTC")
TEST_END = pd.Timestamp("2026-09-08 23:59:59", tz="UTC")
WARMUP_START = TEST_START - pd.Timedelta(days=120)
RISK_PCT = 0.0036
COST_R = 0.05


def vwma(df: pd.DataFrame, n: int) -> pd.Series:
    typ = (df.high + df.low + df.close) / 3.0
    v = df.tick_volume.astype(float)
    return (typ * v).rolling(n, min_periods=n).sum() / v.rolling(n, min_periods=n).sum()


def add_vwma_z(df: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    x = df.copy()
    for n in sorted(set(periods + [48, 84])):
        x[f"vwma{n}"] = vwma(x, n)
        sd = x.close.rolling(n, min_periods=n).std(ddof=0).replace(0, np.nan)
        x[f"z{n}"] = (x.close - x[f"vwma{n}"]) / sd
    return x


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.resample(rule, origin="epoch", label="left", closed="left")
    out = g.agg({"open":"first","high":"max","low":"min","close":"last","tick_volume":"sum"})
    cnt = g.close.count()
    expected = int(pd.Timedelta(rule) / pd.Timedelta(minutes=5))
    out = out[cnt == expected]
    return out.dropna()


def add_vwap_gates(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    typ = (x.high + x.low + x.close) / 3.0
    vol = x.tick_volume.clip(lower=1).astype(float)
    pv = typ * vol
    idx = x.index

    day = pd.Series(idx.strftime("%Y-%m-%d"), index=idx)
    iso = idx.isocalendar()
    week = pd.Series(iso.year.astype(str) + "-" + iso.week.astype(str), index=idx)
    mins = idx.hour * 60 + idx.minute
    sess_name = np.where(mins < 480, "A", np.where(mins < 810, "L", "N"))
    sess = pd.Series(idx.strftime("%Y-%m-%d") + "_" + sess_name, index=idx)

    def cumulative_with_prior(groups: pd.Series, prefix: str):
        current = pv.groupby(groups).cumsum() / vol.groupby(groups).cumsum()
        final = current.groupby(groups).transform("last")
        codes, uniques = pd.factorize(groups, sort=False)
        final_by_code = pd.Series(final.groupby(codes).last().to_numpy())
        prior_vals = np.full(len(x), np.nan)
        good = codes > 0
        prior_vals[good] = final_by_code.iloc[codes[good]-1].to_numpy()
        x[f"{prefix}_vwap"] = current
        x[f"{prefix}_prior"] = prior_vals

    cumulative_with_prior(sess, "sess")
    cumulative_with_prior(day, "day")
    cumulative_with_prior(week, "week")
    return x


def profile_levels(window: pd.DataFrame, bins: int = 24, value_area: float = 0.70):
    if len(window) < 8:
        return (np.nan, np.nan, np.nan)
    lo = float(window.low.min()); hi = float(window.high.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return (np.nan, np.nan, np.nan)
    edges = np.linspace(lo, hi, bins+1)
    vols = np.zeros(bins, dtype=float)
    for r in window.itertuples():
        a = max(0, min(bins-1, int(np.searchsorted(edges, r.low, side="right")-1)))
        b = max(0, min(bins-1, int(np.searchsorted(edges, r.high, side="left")-1)))
        if b < a: b = a
        share = float(r.tick_volume) / (b-a+1)
        vols[a:b+1] += share
    if vols.sum() <= 0:
        return (np.nan, np.nan, np.nan)
    poc = int(np.argmax(vols))
    chosen = {poc}; total = vols[poc]; target = vols.sum()*value_area
    left, right = poc-1, poc+1
    while total < target and (left >= 0 or right < bins):
        lv = vols[left] if left >= 0 else -1
        rv = vols[right] if right < bins else -1
        if rv > lv:
            chosen.add(right); total += rv; right += 1
        else:
            chosen.add(left); total += lv; left -= 1
    low_bin, high_bin = min(chosen), max(chosen)
    poc_px = (edges[poc] + edges[poc+1]) / 2
    val = edges[low_bin]; vah = edges[high_bin+1]
    return poc_px, vah, val


def load_data():
    print("DOWNLOAD", DATA_URL, flush=True)
    d = pd.read_csv(DATA_URL)
    d["time"] = pd.to_datetime(d.time, utc=True)
    d = d[(d.time >= WARMUP_START) & (d.time <= TEST_END)].copy()
    d = d.drop_duplicates("time").sort_values("time").set_index("time")
    for c in ["open","high","low","close","tick_volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna()
    m5 = add_vwma_z(d, [84,175])
    typ = (m5.high+m5.low+m5.close)/3.0
    m5["dv"] = typ*m5.tick_volume
    m5["dvma30"] = m5.dv.rolling(30, min_periods=30).mean()
    m5["rqvol"] = m5.dvma30 / m5.dvma30.rolling(1800, min_periods=500).mean()
    m5 = add_vwap_gates(m5)
    m5["z48_prevmax20"] = m5.z48.shift(1).rolling(20, min_periods=10).max()
    m5["z84_prevmax20"] = m5.z84.shift(1).rolling(20, min_periods=10).max()
    m5["z48_prevmin20"] = m5.z48.shift(1).rolling(20, min_periods=10).min()
    m5["z84_prevmin20"] = m5.z84.shift(1).rolling(20, min_periods=10).min()

    m15 = add_vwma_z(resample(d, "15min"), [21,175,480,840])
    h1 = add_vwma_z(resample(d, "1h"), [21,84,175,480,840])
    print("RANGE", d.index.min(), d.index.max(), "M5", len(m5), "M15", len(m15), "H1", len(h1), flush=True)
    return m5, m15, h1


def attach_context(m5: pd.DataFrame, m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    base = m5.copy()
    base["decision_time"] = base.index + pd.Timedelta(minutes=5)

    q15 = m15.copy()
    q15["ctx_time"] = q15.index + pd.Timedelta(minutes=15)
    q15["m15_time"] = q15.index
    q15cols = ["ctx_time","m15_time","close","low","high","vwma21","vwma175","vwma480","vwma840"]
    merged = pd.merge_asof(base.reset_index().sort_values("decision_time"), q15[q15cols].sort_values("ctx_time"), left_on="decision_time", right_on="ctx_time", direction="backward", suffixes=("","_15"))

    q1 = h1.copy()
    q1["ctx_time_h1"] = q1.index + pd.Timedelta(hours=1)
    q1["h1_time"] = q1.index
    hcols = ["ctx_time_h1","h1_time","close","vwma21","vwma84","vwma175","vwma480","vwma840"]
    merged = pd.merge_asof(merged.sort_values("decision_time"), q1[hcols].sort_values("ctx_time_h1"), left_on="decision_time", right_on="ctx_time_h1", direction="backward", suffixes=("","_h1"))
    return merged.set_index("time").sort_index()


def base_flags(x: pd.DataFrame):
    # Higher-timeframe regimes: medium is deliberately less restrictive than a perfect full stack.
    hlong = (x.close_h1 > x.vwma84_h1) & (x.vwma84_h1 > x.vwma175_h1) & (x.vwma175_h1 > x.vwma480_h1)
    hshort = (x.close_h1 < x.vwma84_h1) & (x.vwma84_h1 < x.vwma175_h1) & (x.vwma175_h1 < x.vwma480_h1)
    mlong = (x.close_15 > x.vwma21_15) & (x.vwma21_15 > x.vwma175_15) & (x.vwma175_15 > x.vwma480_15)
    mshort = (x.close_15 < x.vwma21_15) & (x.vwma21_15 < x.vwma175_15) & (x.vwma175_15 < x.vwma480_15)

    # 15m pullback evidence in the just-closed context bar: body remains around/above the structural 175 tier.
    pull_l = (x.low_15 <= x.vwma21_15 * 1.0025) & (x.close_15 > x.vwma175_15 * 0.997)
    pull_s = (x.high_15 >= x.vwma21_15 * 0.9975) & (x.close_15 < x.vwma175_15 * 1.003)

    # 5m execution: reclaim VWMA84 while respecting VWMA175, plus break of previous candle extreme.
    prev_close = x.close.shift(1); prev84 = x.vwma84.shift(1)
    trig_l = (prev_close <= prev84) & (x.close > x.vwma84) & (x.close > x.vwma175) & (x.close > x.high.shift(1))
    trig_s = (prev_close >= prev84) & (x.close < x.vwma84) & (x.close < x.vwma175) & (x.close < x.low.shift(1))
    return (hlong & mlong & pull_l & trig_l).fillna(False), (hshort & mshort & pull_s & trig_s).fillna(False)


def vwap_flags(x: pd.DataFrame):
    l = ((x.sess_vwap > x.sess_prior) & (x.day_vwap > x.day_prior) & (x.week_vwap > x.week_prior) &
         (x.close > x.sess_vwap) & (x.close > x.sess_prior) & (x.close > x.day_vwap) & (x.close > x.day_prior) &
         (x.close > x.week_vwap) & (x.close > x.week_prior))
    s = ((x.sess_vwap < x.sess_prior) & (x.day_vwap < x.day_prior) & (x.week_vwap < x.week_prior) &
         (x.close < x.sess_vwap) & (x.close < x.sess_prior) & (x.close < x.day_vwap) & (x.close < x.day_prior) &
         (x.close < x.week_vwap) & (x.close < x.week_prior))
    return l.fillna(False), s.fillna(False)


def flow_flags(x: pd.DataFrame):
    common = (x.dv > x.dvma30) & (x.rqvol > 1.0)
    return common.fillna(False), common.fillna(False)


def z_flags(x: pd.DataFrame):
    # Strict re-acceleration: both native Z series exceed their own recent pre-signal maxima/minima.
    l = (x.z48 > x.z48_prevmax20) & (x.z84 > x.z84_prevmax20) & (x.z48 > 0) & (x.z84 > 0)
    s = (x.z48 < x.z48_prevmin20) & (x.z84 < x.z84_prevmin20) & (x.z48 < 0) & (x.z84 < 0)
    return l.fillna(False), s.fillna(False)


def add_profile_flags(x: pd.DataFrame, m15: pd.DataFrame, candidate_mask: pd.Series):
    prof_l = pd.Series(False, index=x.index); prof_s = pd.Series(False, index=x.index)
    cache = {}
    m15_pos = pd.Series(np.arange(len(m15)), index=m15.index)
    for ts in x.index[candidate_mask]:
        mt = x.at[ts, "m15_time"]
        if pd.isna(mt) or mt not in m15_pos.index: continue
        p = int(m15_pos.loc[mt])
        if p not in cache:
            w = m15.iloc[max(0,p-31):p+1]
            fixed = profile_levels(w)
            day = m15.index[p].date()
            day_start = p
            while day_start > 0 and m15.index[day_start-1].date() == day:
                day_start -= 1
            developing = profile_levels(m15.iloc[day_start:p+1])
            cache[p] = (fixed, developing)
        (fpoc,fvah,fval),(dpoc,dvah,dval) = cache[p]
        px = float(x.at[ts,"close"])
        if np.isfinite(fvah) and np.isfinite(dpoc):
            prof_l.at[ts] = px > fvah and px > dpoc
            prof_s.at[ts] = px < fval and px < dpoc
    return prof_l, prof_s


@dataclass
class Result:
    name: str
    side: str
    exit_style: str
    trades: int
    win_rate: float
    ret: float
    max_dd: float
    pf: float
    avg_r: float
    median_r: float
    avg_hours: float
    median_hours: float
    fold_returns: list[float]
    fold_trades: list[int]


def simulate(x: pd.DataFrame, long_sig: pd.Series, short_sig: pd.Series, exit_style: str, long_only: bool, start: pd.Timestamp, end: pd.Timestamp):
    idx = x.index
    mask_range = (idx >= start) & (idx < end)
    arr = np.flatnonzero(mask_range.to_numpy())
    if len(arr) == 0: return [], []
    i = max(arr[0], 20); last = arr[-1]
    rs=[]; durs=[]
    while i < last-1:
        direction = 0
        if bool(long_sig.iloc[i]): direction = 1
        elif not long_only and bool(short_sig.iloc[i]): direction = -1
        if direction == 0:
            i += 1; continue
        entry_i = i+1
        entry = float(x.open.iloc[entry_i])
        if direction == 1:
            protected = min(float(x.low.iloc[max(0,i-11):i+1].min()), float(x.vwma175.iloc[i]))
            stop = protected * (1-0.0025)
            risk = entry-stop
        else:
            protected = max(float(x.high.iloc[max(0,i-11):i+1].max()), float(x.vwma175.iloc[i]))
            stop = protected * (1+0.0025)
            risk = stop-entry
        if not np.isfinite(risk) or risk <= 0 or risk/entry > 0.025:
            i += 1; continue
        remain=1.0; realized=0.0; hit2=False; best=entry; active_stop=stop
        exit_i=None
        max_j=min(last, entry_i+144)  # maximum 12 hours
        for j in range(entry_i, max_j+1):
            hi=float(x.high.iloc[j]); lo=float(x.low.iloc[j])
            # trailing level is based only on favorable extremes from PRIOR bars.
            if exit_style == "trail" and hit2:
                if direction==1: active_stop=max(stop, entry, best-2.0*risk)
                else: active_stop=min(stop, entry, best+2.0*risk)
            stop_hit = lo <= active_stop if direction==1 else hi >= active_stop
            if stop_hit:
                rstop = direction*(active_stop-entry)/risk
                realized += remain*rstop; remain=0; exit_i=j; break
            favorable = (hi-entry)/risk if direction==1 else (entry-lo)/risk
            if exit_style == "3R":
                if favorable >= 3:
                    realized=3.0; remain=0; exit_i=j; break
            else:
                if remain > 0.80-1e-9 and favorable >= 2:
                    realized += 0.2*2; remain -= 0.2
                if remain > 0.60-1e-9 and favorable >= 4:
                    realized += 0.2*4; remain -= 0.2; hit2=True
                if exit_style == "scale6" and favorable >= 6:
                    realized += remain*6; remain=0; exit_i=j; break
            # update best only for the next bar's trail
            if direction==1: best=max(best,hi)
            else: best=min(best,lo)
        if exit_i is None:
            exit_i=max_j
            px=float(x.close.iloc[exit_i])
            realized += remain*direction*(px-entry)/risk
        net_r = realized - COST_R
        rs.append(net_r)
        durs.append((idx[exit_i]-idx[entry_i]).total_seconds()/3600.0)
        i=max(i+1,exit_i+1)
    return rs,durs


def metrics(name, side, style, rs, durs, folds, fold_ns):
    if not rs: return None
    a=np.asarray(rs,float); eq=1.0; peak=1.0; dd=0.0
    for r in a:
        eq *= max(0.001, 1 + RISK_PCT*r)
        peak=max(peak,eq); dd=max(dd,(peak-eq)/peak)
    gp=a[a>0].sum(); gl=-a[a<0].sum()
    return Result(name,side,style,len(a),100*(a>0).mean(),100*(eq-1),100*dd,float(gp/gl if gl>0 else 99),float(a.mean()),float(np.median(a)),float(np.mean(durs)),float(np.median(durs)),folds,fold_ns)


def main():
    m5,m15,h1 = load_data()
    x = attach_context(m5,m15,h1)
    x = x[(x.index >= WARMUP_START) & (x.index <= TEST_END)].copy()
    base_l,base_s = base_flags(x)
    vw_l,vw_s = vwap_flags(x)
    fl_l,fl_s = flow_flags(x)
    z_l,z_s = z_flags(x)
    candidate = base_l | base_s
    pr_l,pr_s = add_profile_flags(x,m15,candidate)

    ladders = {
        "VWMA_ONLY": (base_l,base_s),
        "VWMA_VWAP": (base_l&vw_l,base_s&vw_s),
        "VWMA_VWAP_FLOW": (base_l&vw_l&fl_l,base_s&vw_s&fl_s),
        "VWMA_VWAP_Z": (base_l&vw_l&z_l,base_s&vw_s&z_s),
        "VWMA_VWAP_PROFILE": (base_l&vw_l&pr_l,base_s&vw_s&pr_s),
        "FULL_AVAILABLE": (base_l&vw_l&fl_l&z_l&pr_l,base_s&vw_s&fl_s&z_s&pr_s),
    }
    fold_starts = list(pd.date_range(TEST_START, TEST_END, freq="6MS"))
    results=[]
    for name,(ls,ss) in ladders.items():
        for long_only in [True,False]:
            side="LONG" if long_only else "BOTH"
            for style in ["3R","scale6","trail"]:
                rs,durs=simulate(x,ls,ss,style,long_only,TEST_START,TEST_END)
                folds=[]; fns=[]
                for fs in fold_starts:
                    fe=min(fs+pd.DateOffset(months=6),TEST_END)
                    fr,fd=simulate(x,ls,ss,style,long_only,fs,fe)
                    if fr:
                        eq=1.0
                        for r in fr: eq*=max(0.001,1+RISK_PCT*r)
                        folds.append(100*(eq-1)); fns.append(len(fr))
                    else:
                        folds.append(0.0); fns.append(0)
                r=metrics(name,side,style,rs,durs,folds,fns)
                if r: results.append(r)

    def obj(r: Result):
        if r.trades < 30: return -1e9
        med=float(np.median(r.fold_returns)); neg=sum(v<0 for v in r.fold_returns)
        return r.ret - 0.7*r.max_dd + 3.0*med - 2.0*neg
    robust=sorted(results,key=obj,reverse=True)
    raw=sorted(results,key=lambda r:r.ret,reverse=True)
    def pack(r):
        return {"name":r.name,"side":r.side,"exit":r.exit_style,"trades":r.trades,"win_rate":round(r.win_rate,2),"return_pct":round(r.ret,2),"max_dd_pct":round(r.max_dd,2),"pf":round(r.pf,3),"avg_r":round(r.avg_r,3),"median_r":round(r.median_r,3),"avg_hours":round(r.avg_hours,2),"median_hours":round(r.median_hours,2),"fold_returns":[round(v,2) for v in r.fold_returns],"fold_trades":r.fold_trades}
    out={
      "risk_per_setup_pct":0.36,
      "roundtrip_cost_assumption_R":COST_R,
      "source":"simom1/XAUUSD-history MT5 XAUUSD M5 tick_volume proxy",
      "limitations":["bar OHLC conservative stop-first, not bid/ask tick execution","tick_volume is activity proxy, not real traded volume","historical news and DXY are not included in this run","fingerprint/trade_count unavailable and therefore not approximated"],
      "best_robust":pack(robust[0]) if robust else None,
      "best_raw_return":pack(raw[0]) if raw else None,
      "top_robust":[pack(r) for r in robust[:12]],
    }
    print("RESULT_JSON_START")
    print(json.dumps(out,ensure_ascii=False))
    print("RESULT_JSON_END")

if __name__ == "__main__":
    main()
