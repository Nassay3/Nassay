import pandas as pd

DATA_ROOT = "https://raw.githubusercontent.com/kevingtlin/dukascopy_XAUUSD_1m_Data/main/xauusd"


def make_configs():
    return [
        {"lookback": lookback, "mode": mode, "liquid_only": liquid_only, "rr": float(rr)}
        for lookback in (20, 60)
        for mode in ("trend", "reversal")
        for liquid_only in (False, True)
        for rr in (2, 3, 4, 6)
    ]


def month_keys(start, end):
    first = pd.Period(start, freq="M")
    last = pd.Period(end, freq="M")
    if last < first:
        raise ValueError("end month must be >= start month")
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def data_urls(month_key):
    year, month = month_key.split("-")
    bid = f"{DATA_ROOT}/bid/m1/xauusd_bid_m1_{year}_{month}.csv"
    ask = f"{DATA_ROOT}/ask/m1/xauusd_ask_m1_{year}_{month}.csv"
    return bid, ask
