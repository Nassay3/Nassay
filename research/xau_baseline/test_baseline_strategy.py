import pandas as pd


def _df(hour=7):
    base = pd.Timestamp(f"2024-01-02 {hour:02d}:00:00", tz="UTC")
    ts = [(base + pd.Timedelta(minutes=i)).value // 1_000_000 for i in range(5)]
    return pd.DataFrame({
        "timestamp": ts,
        "datetime_utc": pd.to_datetime(ts, unit="ms", utc=True),
        "bid_open":  [10.0, 10.2, 10.4, 10.4, 10.5],
        "bid_high":  [10.3, 10.5, 10.7, 10.6, 10.8],
        "bid_low":   [9.8, 10.0, 10.1, 9.7, 10.2],
        "bid_close": [10.0, 10.2, 10.4, 10.5, 10.6],
        "ask_open":  [20.0, 20.2, 20.4, 20.4, 20.5],
        "ask_high":  [20.3, 20.5, 20.7, 20.6, 20.8],
        "ask_low":   [19.8, 20.0, 20.1, 19.7, 20.2],
        "ask_close": [20.0, 20.2, 20.4, 20.5, 20.6],
    })


def test_trend_long_requires_sweep_and_positive_bid_stack():
    from baseline_strategy import build_signals
    df = _df()
    sig = build_signals(df, lookback=3, mode="trend", liquid_only=False,
                        fast_window=2, slow_window=3, atr_window=2)
    assert bool(sig["long_signal"].iloc[3]) is True
    assert bool(sig["short_signal"].iloc[3]) is False
    assert sig["long_stop"].iloc[3] < df["bid_low"].iloc[3]


def test_reversal_does_not_take_same_positive_stack_long():
    from baseline_strategy import build_signals
    df = _df()
    sig = build_signals(df, lookback=3, mode="reversal", liquid_only=False,
                        fast_window=2, slow_window=3, atr_window=2)
    assert bool(sig["long_signal"].iloc[3]) is False


def test_liquid_only_blocks_signal_before_0600_utc():
    from baseline_strategy import build_signals
    df = _df(hour=5)
    sig = build_signals(df, lookback=3, mode="trend", liquid_only=True,
                        fast_window=2, slow_window=3, atr_window=2)
    assert bool(sig["long_signal"].iloc[3]) is False


def test_signal_is_independent_of_ask_structure_columns():
    from baseline_strategy import build_signals
    df1 = _df(); df2 = _df()
    df2[["ask_open", "ask_high", "ask_low", "ask_close"]] += 1000.0
    a = build_signals(df1, lookback=3, mode="trend", liquid_only=False,
                      fast_window=2, slow_window=3, atr_window=2)
    b = build_signals(df2, lookback=3, mode="trend", liquid_only=False,
                      fast_window=2, slow_window=3, atr_window=2)
    assert a["long_signal"].tolist() == b["long_signal"].tolist()
    assert a["short_signal"].tolist() == b["short_signal"].tolist()
