#!/usr/bin/env python3
"""Unit-agnostic VWAP period grouping for XAUUSD research."""
import numpy as np
import pandas as pd


def _period_vwap(tp: pd.Series, volume: pd.Series, key: pd.Series):
    pv = tp * volume
    cur = pv.groupby(key).cumsum() / volume.groupby(key).cumsum().replace(0, np.nan)
    final = pd.DataFrame({'key': key, 'vwap': cur}).groupby('key', sort=True).vwap.last()
    prev = key.map(final.shift(1))
    return cur, prev


def vwap_context(base: pd.DataFrame) -> pd.DataFrame:
    x = base.copy()
    tp = (x.high + x.low + x.close) / 3.0
    volume = x.volume.astype(float)

    # Do not convert timestamps to raw int64: pandas 3 may use microseconds.
    day = x.time.dt.floor('D')
    week = day - pd.to_timedelta(day.dt.weekday, unit='D')
    minute = x.time.dt.hour * 60 + x.time.dt.minute
    session_no = np.where(minute < 480, 0, np.where(minute < 870, 1, 2)).astype(np.int64)

    day_codes = pd.factorize(day, sort=False)[0].astype(np.int64)
    session_key = pd.Series(day_codes * 3 + session_no, index=x.index)

    x['d_vwap'], x['prev_d_vwap'] = _period_vwap(tp, volume, day)
    x['w_vwap'], x['prev_w_vwap'] = _period_vwap(tp, volume, week)
    x['s_vwap'], x['prev_s_vwap'] = _period_vwap(tp, volume, session_key)
    x['session'] = np.where(session_no == 0, 'ASIA', np.where(session_no == 1, 'LONDON', 'NEW_YORK'))
    x['ctx_time'] = x.time + pd.Timedelta(minutes=15)

    return x[['ctx_time','d_vwap','prev_d_vwap','w_vwap','prev_w_vwap','s_vwap','prev_s_vwap','session']]
