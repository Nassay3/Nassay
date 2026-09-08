import math
import pandas as pd


def test_compounding_uses_exact_point_36_percent_risk():
    from backtest_core import compound_equity
    got = compound_equity([2.0, -1.0], risk_fraction=0.0036)
    expected = (1 + 2.0 * 0.0036) * (1 - 0.0036)
    assert math.isclose(got, expected, rel_tol=0, abs_tol=1e-12)


def test_next_bar_entry_uses_ask_for_long_and_bid_for_short():
    from backtest_core import next_bar_entry
    df = pd.DataFrame({"ask_open": [100.4, 101.4], "bid_open": [100.0, 101.0]})
    assert next_bar_entry(df, signal_index=0, side="long") == 101.4
    assert next_bar_entry(df, signal_index=0, side="short") == 101.0


def test_same_bar_stop_and_target_collision_is_stop_first_long_and_short():
    from backtest_core import resolve_bar_r
    assert resolve_bar_r("long", stop=99.0, target=103.0, rr=3.0,
                         bid_low=98.0, bid_high=104.0, ask_low=98.4, ask_high=104.4) == -1.0
    assert resolve_bar_r("short", stop=104.0, target=100.0, rr=3.0,
                         bid_low=99.0, bid_high=103.5, ask_low=99.4, ask_high=104.5) == -1.0


def test_sweep_uses_only_prior_bars_not_current_bar():
    from backtest_core import sweep_flags
    df = pd.DataFrame({
        "bid_high": [10.0, 10.2, 10.1, 10.0],
        "bid_low":  [9.0,  9.2,  9.1,  8.8],
        "bid_close":[9.5,  9.6,  9.5,  9.3],
    })
    long_sweep, short_sweep = sweep_flags(df, lookback=3)
    assert bool(long_sweep.iloc[3]) is True
    assert bool(short_sweep.iloc[3]) is False
