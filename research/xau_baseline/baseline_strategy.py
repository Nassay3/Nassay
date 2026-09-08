import pandas as pd

from backtest_core import sweep_flags


def build_signals(df, *, lookback, mode, liquid_only,
                  fast_window=84, slow_window=175, atr_window=14,
                  stop_atr_pad=0.10):
    close = df["bid_close"].astype(float)
    high = df["bid_high"].astype(float)
    low = df["bid_low"].astype(float)

    fast = close.rolling(fast_window).mean()
    slow = close.rolling(slow_window).mean()
    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = true_range.rolling(atr_window).mean()

    sweep_long, sweep_short = sweep_flags(df, lookback)
    bullish = (close > fast) & (fast > slow)
    bearish = (close < fast) & (fast < slow)

    if mode == "trend":
        long_signal = sweep_long & bullish
        short_signal = sweep_short & bearish
    elif mode == "reversal":
        long_signal = sweep_long & bearish
        short_signal = sweep_short & bullish
    else:
        raise ValueError("mode must be trend or reversal")

    if liquid_only:
        dt = df["datetime_utc"]
        minute_of_day = dt.dt.hour * 60 + dt.dt.minute
        liquid = (minute_of_day >= 360) & (minute_of_day <= 1260)
        long_signal = long_signal & liquid
        short_signal = short_signal & liquid

    valid = atr.notna() & (atr > 0)
    out = pd.DataFrame(index=df.index)
    out["long_signal"] = (long_signal & valid).fillna(False)
    out["short_signal"] = (short_signal & valid).fillna(False)
    out["long_stop"] = low - float(stop_atr_pad) * atr
    out["short_stop"] = high + float(stop_atr_pad) * atr
    out["atr"] = atr
    out["fast"] = fast
    out["slow"] = slow
    return out
