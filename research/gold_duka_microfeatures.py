import numpy as np
import pandas as pd


def compute_features(exe: pd.DataFrame) -> pd.DataFrame:
    """Causal price/execution features from Dukascopy M1 BID/ASK OHLC.

    These are deliberately NOT labeled CVD/TPS/order-book imbalance because this
    dataset has neither trades nor depth. Row t uses only rows <= t.
    """
    z = exe.copy().reset_index(drop=True)
    mid_o = (z.open_bid.astype(float) + z.open_ask.astype(float)) / 2.0
    mid_h = (z.high_bid.astype(float) + z.high_ask.astype(float)) / 2.0
    mid_l = (z.low_bid.astype(float) + z.low_ask.astype(float)) / 2.0
    mid_c = (z.close_bid.astype(float) + z.close_ask.astype(float)) / 2.0

    spread = (z.close_ask.astype(float) - z.close_bid.astype(float)).clip(lower=0.0)
    spr_med60 = spread.rolling(60, min_periods=10).median()
    spread_ratio = spread / spr_med60.replace(0.0, np.nan)
    spread_change = spread.pct_change(5).replace([np.inf, -np.inf], np.nan)

    mom1 = mid_c.pct_change(1)
    mom5 = mid_c.pct_change(5)
    mom15 = mid_c.pct_change(15)

    hi5 = mid_h.rolling(5, min_periods=5).max()
    lo5 = mid_l.rolling(5, min_periods=5).min()
    rng5 = (hi5 - lo5).replace(0.0, np.nan)
    clv5 = ((mid_c - lo5) / rng5 - 0.5) * 2.0

    # Directional candle-pressure proxy from price only: signed body / total range,
    # then smoothed over the most recent 5 completed/current M1 bars.
    bar_rng = (mid_h - mid_l).replace(0.0, np.nan)
    body_pressure = ((mid_c - mid_o) / bar_rng).clip(-1.0, 1.0)
    pressure5 = body_pressure.rolling(5, min_periods=5).mean()

    # Five-minute realized range relative to its causal 60-minute rolling median.
    range_med60 = rng5.rolling(60, min_periods=10).median()
    range_exp5 = rng5 / range_med60.replace(0.0, np.nan)

    out = pd.DataFrame({
        'spread': spread,
        'spread_ratio': spread_ratio,
        'spread_change': spread_change,
        'mom1': mom1,
        'mom5': mom5,
        'mom15': mom15,
        'clv5': clv5,
        'range_exp5': range_exp5,
        'pressure5': pressure5,
    }, index=z.index)
    return out
