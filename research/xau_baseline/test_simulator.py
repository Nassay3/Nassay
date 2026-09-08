import math
import pandas as pd


def _frame():
    return pd.DataFrame({
        "timestamp": [0, 60_000, 120_000, 180_000],
        "bid_open":  [100.0, 100.6, 101.8, 102.8],
        "bid_high":  [100.4, 102.0, 103.2, 103.0],
        "bid_low":   [99.8, 100.4, 101.5, 102.5],
        "bid_close": [100.2, 101.8, 103.0, 102.9],
        "ask_open":  [100.4, 101.0, 102.2, 103.2],
        "ask_high":  [100.8, 102.4, 103.6, 103.4],
        "ask_low":   [100.2, 100.8, 101.9, 102.9],
        "ask_close": [100.6, 102.2, 103.4, 103.3],
    })


def test_long_signal_enters_next_bar_and_hits_2r():
    from simulator import simulate_signals
    df = _frame()
    long_signal = pd.Series([True, False, False, False])
    short_signal = pd.Series([False] * 4)
    long_stop = pd.Series([100.0] * 4)
    short_stop = pd.Series([104.0] * 4)
    result, trades = simulate_signals(df, long_signal, short_signal, long_stop, short_stop, rr=2.0, max_hold_bars=10)
    assert result["trades"] == 1
    assert math.isclose(result["sum_r"], 2.0)
    assert trades[0]["entry_index"] == 1
    assert trades[0]["entry_price"] == 101.0
    assert trades[0]["exit_index"] == 2
    assert trades[0]["exit_reason"] == "target"


def test_signal_while_position_open_does_not_overlap():
    from simulator import simulate_signals
    df = _frame()
    long_signal = pd.Series([True, True, False, False])
    short_signal = pd.Series([False] * 4)
    stop = pd.Series([100.0] * 4)
    result, trades = simulate_signals(df, long_signal, short_signal, stop, pd.Series([104.0] * 4), rr=2.0, max_hold_bars=10)
    assert result["trades"] == 1
    assert len(trades) == 1


def test_equity_and_drawdown_use_point_36_percent_per_r():
    from simulator import summarize_rs
    result = summarize_rs([2.0, -1.0], risk_fraction=0.0036)
    expected = (1 + 2 * 0.0036) * (1 - 0.0036)
    assert math.isclose(result["equity_multiple"], expected, rel_tol=0, abs_tol=1e-12)
    assert result["max_dd_pct"] > 0
