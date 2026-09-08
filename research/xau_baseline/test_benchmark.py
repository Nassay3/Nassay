def test_matrix_is_exactly_32_unique_preregistered_configs():
    from benchmark import make_configs
    configs = make_configs()
    assert len(configs) == 32
    keys = {(c["lookback"], c["mode"], c["liquid_only"], c["rr"]) for c in configs}
    assert len(keys) == 32
    assert {c["lookback"] for c in configs} == {20, 60}
    assert {c["mode"] for c in configs} == {"trend", "reversal"}
    assert {c["liquid_only"] for c in configs} == {False, True}
    assert {c["rr"] for c in configs} == {2.0, 3.0, 4.0, 6.0}


def test_month_keys_are_inclusive_and_chronological():
    from benchmark import month_keys
    assert month_keys("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_data_urls_point_to_verified_public_bid_and_ask_files():
    from benchmark import data_urls
    bid, ask = data_urls("2024-01")
    assert bid.endswith("/xauusd/bid/m1/xauusd_bid_m1_2024_01.csv")
    assert ask.endswith("/xauusd/ask/m1/xauusd_ask_m1_2024_01.csv")
    assert "dukascopy_XAUUSD_1m_Data" in bid
    assert "dukascopy_XAUUSD_1m_Data" in ask
