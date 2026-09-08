import pandas as pd


def test_merge_bid_ask_is_inner_timestamp_join_and_names_sides(tmp_path):
    from data_io import load_bid_ask_pair

    bid = pd.DataFrame({
        "timestamp": [1000, 2000, 3000],
        "open": [10.0, 11.0, 12.0], "high": [10.5, 11.5, 12.5],
        "low": [9.5, 10.5, 11.5], "close": [10.2, 11.2, 12.2],
    })
    ask = pd.DataFrame({
        "timestamp": [2000, 3000, 4000],
        "open": [11.3, 12.3, 13.3], "high": [11.8, 12.8, 13.8],
        "low": [10.8, 11.8, 12.8], "close": [11.5, 12.5, 13.5],
    })
    bp = tmp_path / "bid.csv"; ap = tmp_path / "ask.csv"
    bid.to_csv(bp, index=False); ask.to_csv(ap, index=False)

    got = load_bid_ask_pair(bp, ap)
    assert got["timestamp"].tolist() == [2000, 3000]
    assert got["bid_open"].tolist() == [11.0, 12.0]
    assert got["ask_open"].tolist() == [11.3, 12.3]
    assert got["spread_open"].round(10).tolist() == [0.3, 0.3]
    assert str(got["datetime_utc"].dt.tz) == "UTC"


def test_merge_rejects_duplicate_timestamps(tmp_path):
    from data_io import load_bid_ask_pair
    import pytest

    bid = pd.DataFrame({"timestamp": [1000, 1000], "open": [1,1], "high": [1,1], "low": [1,1], "close": [1,1]})
    ask = pd.DataFrame({"timestamp": [1000], "open": [2], "high": [2], "low": [2], "close": [2]})
    bp = tmp_path / "bid.csv"; ap = tmp_path / "ask.csv"
    bid.to_csv(bp, index=False); ask.to_csv(ap, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        load_bid_ask_pair(bp, ap)
