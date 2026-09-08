import math
import pandas as pd


def test_run_matrix_composes_signal_and_execution_without_lookahead():
    from benchmark import run_matrix

    base = pd.Timestamp("2024-01-02 07:00:00", tz="UTC")
    ts = [(base + pd.Timedelta(minutes=i)).value // 1_000_000 for i in range(7)]
    df = pd.DataFrame({
        "timestamp": ts,
        "datetime_utc": pd.to_datetime(ts, unit="ms", utc=True),
        "bid_open":  [10.0, 10.2, 10.4, 10.4, 10.5, 11.5, 12.5],
        "bid_high":  [10.3, 10.5, 10.7, 10.6, 11.2, 12.2, 13.2],
        "bid_low":   [9.8, 10.0, 10.1, 9.7, 10.3, 11.2, 12.2],
        "bid_close": [10.0, 10.2, 10.4, 10.5, 11.0, 12.0, 13.0],
        "ask_open":  [10.2, 10.4, 10.6, 10.6, 10.7, 11.7, 12.7],
        "ask_high":  [10.5, 10.7, 10.9, 10.8, 11.4, 12.4, 13.4],
        "ask_low":   [10.0, 10.2, 10.3, 9.9, 10.5, 11.4, 12.4],
        "ask_close": [10.2, 10.4, 10.6, 10.7, 11.2, 12.2, 13.2],
    })
    config = {"lookback": 3, "mode": "trend", "liquid_only": False, "rr": 2.0}
    results, logs = run_matrix(
        df,
        configs=[config],
        feature_kwargs={"fast_window": 2, "slow_window": 3, "atr_window": 2},
        max_hold_bars=10,
    )
    row = results.iloc[0]
    assert row["config_id"] == "L3_trend_all_R2"
    assert row["trades"] == 1
    assert math.isclose(row["sum_r"], 2.0)
    assert row["long_trades"] == 1
    assert row["short_trades"] == 0
    assert len(logs[row["config_id"]]) == 1
