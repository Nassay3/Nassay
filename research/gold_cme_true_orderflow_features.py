"""Build causal TRUE CME GC order-flow features from Databento GLBX.MDP3.

Requires env DATABENTO_API_KEY.  This file intentionally refuses to fall back to
CFD/tick-volume proxies: every feature emitted here comes from CME trade prints or
MBP-10 book state/events.

Recommended symbol: GC.v.0 with stype_in='continuous' (volume-ranked front contract).
All 1m/5m/15m features are timestamped at BAR CLOSE so an XAUUSD M5 decision can
merge_asof backward without lookahead.
"""
from __future__ import annotations
import argparse, os
from pathlib import Path
import numpy as np
import pandas as pd

DATASET = "GLBX.MDP3"
SYMBOL = "GC.v.0"


def _require_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is required; refusing proxy/fallback data")
    return key


def fetch_gc(start: str, end: str):
    import databento as db
    client = db.Historical(_require_key())
    common = dict(dataset=DATASET, symbols=SYMBOL, stype_in="continuous", start=start, end=end)
    trades = client.timeseries.get_range(schema="trades", **common).to_df()
    mbp10 = client.timeseries.get_range(schema="mbp-10", **common).to_df()
    return trades, mbp10


def _ensure_ts_index(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    if not isinstance(z.index, pd.DatetimeIndex):
        for c in ("ts_event", "ts_recv"):
            if c in z.columns:
                z[c] = pd.to_datetime(z[c], utc=True)
                z = z.set_index(c)
                break
    z.index = pd.to_datetime(z.index, utc=True)
    return z.sort_index()


def trade_features(trades: pd.DataFrame, rule: str, minutes: int) -> pd.DataFrame:
    t = _ensure_ts_index(trades)
    side = t["side"].astype(str)
    size = pd.to_numeric(t["size"], errors="coerce").fillna(0.0)
    known = side.isin(["B", "A"])
    buy = size.where(side.eq("B"), 0.0)       # buyer aggressor
    sell = size.where(side.eq("A"), 0.0)      # seller aggressor
    signed = buy - sell
    known_sz = buy + sell

    q = pd.DataFrame(index=t.index)
    q["trade_size"] = size
    q["known_size"] = known_sz
    q["buy_size"] = buy
    q["sell_size"] = sell
    q["signed_size"] = signed
    q["known_trade"] = known.astype(np.int8)
    q["buy_trade"] = side.eq("B").astype(np.int8)
    q["sell_trade"] = side.eq("A").astype(np.int8)

    r = q.resample(rule, origin="epoch", label="left", closed="left").agg(
        volume=("trade_size", "sum"), known_volume=("known_size", "sum"),
        buy_volume=("buy_size", "sum"), sell_volume=("sell_size", "sum"),
        delta=("signed_size", "sum"), trades=("trade_size", "size"),
        known_trades=("known_trade", "sum"), buy_trades=("buy_trade", "sum"),
        sell_trades=("sell_trade", "sum"), avg_trade_size=("trade_size", "mean"),
    )
    den = r["known_volume"].replace(0, np.nan)
    r["cvd"] = r["delta"].cumsum()  # session-unaware long-run CVD; use delta for stationary models
    r["delta_pct_known"] = r["delta"] / den
    r["buy_pressure"] = r["buy_volume"] / den
    r["sell_pressure"] = r["sell_volume"] / den
    r["aggressor_imbalance"] = (r["buy_volume"] - r["sell_volume"]) / den
    r["trade_count_imbalance"] = (r["buy_trades"] - r["sell_trades"]) / r["known_trades"].replace(0, np.nan)
    r["side_known_pct"] = r["known_trades"] / r["trades"].replace(0, np.nan)
    r["tps"] = r["trades"] / float(minutes * 60)
    for c in ("volume", "tps", "avg_trade_size", "delta"):
        r[f"{c}_change_pct"] = r[c].pct_change().replace([np.inf, -np.inf], np.nan)
    # Causal activity baselines use only prior completed buckets.
    r["tps_rel30"] = r["tps"] / r["tps"].shift(1).rolling(30, min_periods=10).median().replace(0, np.nan)
    r["volume_rel30"] = r["volume"] / r["volume"].shift(1).rolling(30, min_periods=10).median().replace(0, np.nan)
    r["avg_trade_size_rel30"] = r["avg_trade_size"] / r["avg_trade_size"].shift(1).rolling(30, min_periods=10).median().replace(0, np.nan)
    r["available_time"] = r.index + pd.Timedelta(minutes=minutes)
    return r


def book_features(mbp10: pd.DataFrame, rule: str, minutes: int) -> pd.DataFrame:
    b = _ensure_ts_index(mbp10)
    # Databento DataFrame columns: bid_px_00..09, ask_px_00..09,
    # bid_sz_00..09, ask_sz_00..09, bid_ct_00..09, ask_ct_00..09.
    bid_sz = [f"bid_sz_{i:02d}" for i in range(10)]
    ask_sz = [f"ask_sz_{i:02d}" for i in range(10)]
    bid_ct = [f"bid_ct_{i:02d}" for i in range(10)]
    ask_ct = [f"ask_ct_{i:02d}" for i in range(10)]
    req = ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "action", "side"] + bid_sz + ask_sz + bid_ct + ask_ct
    missing = [c for c in req if c not in b.columns]
    if missing:
        raise ValueError(f"MBP-10 missing expected fields: {missing[:8]}")

    z = pd.DataFrame(index=b.index)
    bp = pd.to_numeric(b["bid_px_00"], errors="coerce")
    ap = pd.to_numeric(b["ask_px_00"], errors="coerce")
    bs0 = pd.to_numeric(b["bid_sz_00"], errors="coerce")
    a_s0 = pd.to_numeric(b["ask_sz_00"], errors="coerce")
    z["mid"] = (bp + ap) / 2.0
    z["spread"] = ap - bp
    z["microprice"] = (bs0 * ap + a_s0 * bp) / (bs0 + a_s0).replace(0, np.nan)
    z["microprice_edge"] = z["microprice"] - z["mid"]

    for n in (1, 5, 10):
        bs = b[bid_sz[:n]].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        ass = b[ask_sz[:n]].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        bc = b[bid_ct[:n]].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        ac = b[ask_ct[:n]].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        z[f"depth_imb_l{n}"] = (bs - ass) / (bs + ass).replace(0, np.nan)
        z[f"order_count_imb_l{n}"] = (bc - ac) / (bc + ac).replace(0, np.nan)
        z[f"bid_depth_l{n}"] = bs
        z[f"ask_depth_l{n}"] = ass

    # Event-derived stack/pull pressure. This is CME book-event data, not candle inference.
    action = b["action"].astype(str)
    side = b["side"].astype(str)
    event_size = pd.to_numeric(b["size"], errors="coerce").fillna(0.0)
    is_add = action.eq("A")
    is_cancel = action.eq("C")
    z["bid_add"] = event_size.where(is_add & side.eq("B"), 0.0)
    z["ask_add"] = event_size.where(is_add & side.eq("A"), 0.0)
    z["bid_cancel"] = event_size.where(is_cancel & side.eq("B"), 0.0)
    z["ask_cancel"] = event_size.where(is_cancel & side.eq("A"), 0.0)

    # Snapshot-style fields use last book state in the completed bucket; event fields sum.
    state_cols = [c for c in z.columns if c not in ("bid_add", "ask_add", "bid_cancel", "ask_cancel")]
    state = z[state_cols].resample(rule, origin="epoch", label="left", closed="left").last()
    events = z[["bid_add", "ask_add", "bid_cancel", "ask_cancel"]].resample(rule, origin="epoch", label="left", closed="left").sum()
    r = state.join(events)
    r["stack_pressure"] = (r["bid_add"] - r["ask_add"]) / (r["bid_add"] + r["ask_add"]).replace(0, np.nan)
    # Positive pull_pressure means ask liquidity pulled more than bid liquidity (bullish liquidity vacuum).
    r["pull_pressure"] = (r["ask_cancel"] - r["bid_cancel"]) / (r["ask_cancel"] + r["bid_cancel"]).replace(0, np.nan)
    r["liquidity_pressure"] = (r["bid_add"] + r["ask_cancel"] - r["ask_add"] - r["bid_cancel"]) / (
        r["bid_add"] + r["ask_cancel"] + r["ask_add"] + r["bid_cancel"]
    ).replace(0, np.nan)
    for c in ("spread", "depth_imb_l1", "depth_imb_l5", "depth_imb_l10", "order_count_imb_l10", "microprice_edge"):
        r[f"{c}_change"] = r[c] - r[c].shift(1)
    r["available_time"] = r.index + pd.Timedelta(minutes=minutes)
    return r


def build_features(trades: pd.DataFrame, mbp10: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for rule, mins, tag in (("1min", 1, "1m"), ("5min", 5, "5m"), ("15min", 15, "15m")):
        tf = trade_features(trades, rule, mins).add_prefix(f"gc_{tag}_trade_")
        bf = book_features(mbp10, rule, mins).add_prefix(f"gc_{tag}_book_")
        # restore a common availability column after prefixing
        tf = tf.rename(columns={f"gc_{tag}_trade_available_time": "available_time"})
        bf = bf.rename(columns={f"gc_{tag}_book_available_time": "available_time"})
        merged = pd.merge(tf.reset_index(), bf.reset_index(), on=[tf.index.name or "index", "available_time"], how="outer")
        merged["tf"] = tag
        frames.append(merged)
    return pd.concat(frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="/tmp/gc_true_orderflow.parquet")
    args = ap.parse_args()
    trades, mbp10 = fetch_gc(args.start, args.end)
    out = build_features(trades, mbp10)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print({"rows": len(out), "out": args.out, "dataset": DATASET, "symbol": SYMBOL, "truth": "CME trades + MBP-10 only"})

if __name__ == "__main__":
    main()
