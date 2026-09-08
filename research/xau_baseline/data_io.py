import pandas as pd


def load_bid_ask_pair(bid_path, ask_path):
    bid = pd.read_csv(bid_path)
    ask = pd.read_csv(ask_path)
    if bid["timestamp"].duplicated().any() or ask["timestamp"].duplicated().any():
        raise ValueError("duplicate timestamps")
    bid = bid.rename(columns={c: f"bid_{c}" for c in ("open", "high", "low", "close")})
    ask = ask.rename(columns={c: f"ask_{c}" for c in ("open", "high", "low", "close")})
    merged = bid.merge(ask, on="timestamp", how="inner", validate="one_to_one").sort_values("timestamp").reset_index(drop=True)
    merged["datetime_utc"] = pd.to_datetime(merged["timestamp"], unit="ms", utc=True)
    merged["spread_open"] = merged["ask_open"] - merged["bid_open"]
    merged["spread_close"] = merged["ask_close"] - merged["bid_close"]
    return merged
