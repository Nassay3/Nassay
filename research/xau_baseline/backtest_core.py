def compound_equity(rs, risk_fraction=0.0036):
    equity = 1.0
    for r in rs:
        equity *= 1.0 + risk_fraction * float(r)
    return equity


def next_bar_entry(df, signal_index, side):
    row = df.iloc[signal_index + 1]
    if side == "long":
        return float(row["ask_open"])
    if side == "short":
        return float(row["bid_open"])
    raise ValueError("side must be long or short")


def resolve_bar_r(side, *, stop, target, rr, bid_low, bid_high, ask_low, ask_high):
    if side == "long":
        if bid_low <= stop:
            return -1.0
        if bid_high >= target:
            return float(rr)
        return None
    if side == "short":
        if ask_high >= stop:
            return -1.0
        if ask_low <= target:
            return float(rr)
        return None
    raise ValueError("side must be long or short")


def sweep_flags(df, lookback):
    prior_low = df["bid_low"].shift(1).rolling(lookback).min()
    prior_high = df["bid_high"].shift(1).rolling(lookback).max()
    long_sweep = (df["bid_low"] < prior_low) & (df["bid_close"] > prior_low)
    short_sweep = (df["bid_high"] > prior_high) & (df["bid_close"] < prior_high)
    return long_sweep.fillna(False), short_sweep.fillna(False)
