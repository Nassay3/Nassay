import math


def test_long_uses_ask_entry_and_bid_exit():
    from engine import trade_r_long
    assert math.isclose(trade_r_long(ask_entry=2001.0, bid_exit=2003.0, stop=2000.0), 2.0)


def test_short_uses_bid_entry_and_ask_exit():
    from engine import trade_r_short
    assert math.isclose(trade_r_short(bid_entry=2003.0, ask_exit=2001.0, stop=2004.0), 2.0)


def test_same_bar_conflict_is_stop_first():
    from engine import resolve_long_bar
    assert resolve_long_bar(bid_low=1999.0, bid_high=2005.0, stop=2000.0, target=2004.0) == -1.0
